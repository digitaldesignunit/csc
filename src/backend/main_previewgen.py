#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import asyncio
import os
from typing import List, Tuple


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from pymongo import AsyncMongoClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from utility import (
    get_db_connectionstring,
    get_snapshot_preview_directory,
    create_logging_timestamp as logts
)
from apps.previewgen import (
    create_snapshot_preview_image,
    crop_preview_whitespace,
    save_preview_image
)


async def initialize_preview_generation() -> Tuple[List[dict], List[str]]:
    """
    Compare snapshot ids in ``component_snapshots`` with rendered previews in
    ``snapshot_previews/``. Return snapshots missing previews and stale files.
    """
    preview_dir = get_snapshot_preview_directory()
    os.makedirs(preview_dir, exist_ok=True)

    preview_images = set()
    for file_name in os.listdir(preview_dir):
        if os.path.isfile(os.path.join(preview_dir, file_name)):
            preview_images.add(os.path.splitext(file_name)[0])

    mongodb_client = AsyncMongoClient(
        get_db_connectionstring()
    )
    mongodb = mongodb_client['csc']
    mongodb_snapshots = mongodb['component_snapshots']

    snapshot_ids = {
        str(snapshot['_id']) async for snapshot in mongodb_snapshots.find(
            {}, {'_id': 1}
        )
    }
    missing_preview_ids = list(snapshot_ids - preview_images)
    stale_preview_ids = list(preview_images - snapshot_ids)

    missing_preview_snapshots = []
    projection = {
        'geometry': 1,
        'color': 1,
    }
    for snapshot_id in missing_preview_ids:
        snapshot = await mongodb_snapshots.find_one(
            {'_id': snapshot_id}, projection
        )
        if snapshot:
            missing_preview_snapshots.append(snapshot)

    await mongodb_client.close()
    return missing_preview_snapshots, stale_preview_ids


if __name__ == '__main__':
    preview_dir = get_snapshot_preview_directory()
    missing_preview_snapshots, stale_preview_ids = asyncio.run(
        initialize_preview_generation()
    )

    if stale_preview_ids:
        for snapshot_id in stale_preview_ids:
            stale_path = os.path.join(preview_dir, f'{snapshot_id}.webp')
            if os.path.isfile(stale_path):
                os.remove(stale_path)
                ts = logts()
                print(
                    f'[PREVIEWGEN] {ts} Deleted stale preview image '
                    f'for {snapshot_id}.'
                )
    else:
        ts = logts()
        print(f'[PREVIEWGEN] {ts} No stale preview images found.')

    if not missing_preview_snapshots:
        ts = logts()
        print(f'[PREVIEWGEN] {ts} All previews are present.')
    else:
        ts = logts()
        print(
            f'[PREVIEWGEN] {ts} Found {len(missing_preview_snapshots)} '
            'missing previews.'
        )
        for snapshot_data in missing_preview_snapshots:
            snapshot_id = snapshot_data['_id']
            ts = logts()
            print(
                f'[PREVIEWGEN] {ts} Generating preview for {snapshot_id}'
            )
            try:
                save_preview_image(
                    crop_preview_whitespace(
                        create_snapshot_preview_image(
                            snapshot_data=snapshot_data,
                            size=800,
                        ),
                        padding=2,
                    ),
                    folder=preview_dir,
                    filename=snapshot_id,
                )
            except ValueError as exc:
                ts = logts()
                print(
                    f'[PREVIEWGEN] {ts} Skipped preview for '
                    f'{snapshot_id}: {exc}'
                )
                continue
            ts = logts()
            print(
                f'[PREVIEWGEN] {ts} Preview for {snapshot_id} generated.'
            )
