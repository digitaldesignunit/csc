"""``seed_materials`` under concurrency (0.6.0.2): several gunicorn workers
start on an empty ``materials`` collection together; the second insert hit
E11000 and gunicorn halted. Duplicate keys are skipped now, nothing else."""

from __future__ import annotations

import asyncio

import pytest
from pymongo import AsyncMongoClient
from pymongo.errors import BulkWriteError

from apps.catalog.api.catalog_common import seed_materials
from apps.catalog.vocab import MATERIAL_SEED


def _run(mongod, db_name, body):
    async def main():
        client = AsyncMongoClient(mongod.uri)
        try:
            collection = client[db_name]['materials']
            return await body(collection)
        finally:
            await client.close()
    return asyncio.run(main())


def test_workers_that_start_together_seed_once_without_an_error(db, mongod, db_name):
    db['materials'].delete_many({})

    async def body(collection):
        # six workers see the collection empty at the same moment
        return await asyncio.gather(*[seed_materials(collection)
                                      for _ in range(6)])

    counts = _run(mongod, db_name, body)
    assert db['materials'].count_documents({}) == len(MATERIAL_SEED)
    assert sum(counts) == len(MATERIAL_SEED)          # every material once


def test_a_second_start_adds_nothing_and_an_edited_list_stays(db, mongod, db_name):
    db['materials'].delete_many({})
    first = _run(mongod, db_name, seed_materials)
    assert first == len(MATERIAL_SEED)
    db['materials'].update_one({'_id': MATERIAL_SEED[0].id},
                               {'$set': {'label': 'Edited by an admin'}})
    assert _run(mongod, db_name, seed_materials) == 0
    assert db['materials'].find_one({'_id': MATERIAL_SEED[0].id})[
        'label'] == 'Edited by an admin'


def test_an_error_other_than_a_duplicate_key_still_stops_the_start(db, mongod, db_name):
    db['materials'].delete_many({})

    class Failing:
        async def count_documents(self, *args, **kwargs):
            return 0

        async def insert_many(self, docs, ordered=True):
            raise BulkWriteError({'writeErrors': [{'code': 121, 'errmsg': 'x'}],
                                  'nInserted': 0})

    async def body(_collection):
        return await seed_materials(Failing())

    with pytest.raises(BulkWriteError):
        _run(mongod, db_name, body)
