"""
Rasterize CSC Grasshopper icon SVGs to 24x24 PNGs.

Source of truth is ``svg/*.svg``; this regenerates ``24x24/*.png`` for use as
Grasshopper UserObject icons. Run inside the conda ``csc`` environment:

    conda run -n csc python resources/gh_icons/rasterize.py

Requires ``cairosvg`` (conda-forge). Pass ``--check`` to only validate that the
exports match the SVG sources without writing missing PNGs as an error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cairosvg

HERE = Path(__file__).resolve().parent
SVG_DIR = HERE / "svg"
PNG_DIR = HERE / "24x24"
SIZE = 24


def rasterize_one(svg_path: Path, png_path: Path) -> None:
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=SIZE,
        output_height=SIZE,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if any svg/ file is missing a matching 24x24/ PNG",
    )
    args = parser.parse_args()

    if not SVG_DIR.is_dir():
        print(f"missing svg dir: {SVG_DIR}", file=sys.stderr)
        return 1
    PNG_DIR.mkdir(parents=True, exist_ok=True)

    svgs = sorted(SVG_DIR.glob("*.svg"))
    if not svgs:
        print(f"no .svg files found in {SVG_DIR}", file=sys.stderr)
        return 1

    missing = []
    for svg_path in svgs:
        png_path = PNG_DIR / f"{svg_path.stem}.png"
        if args.check:
            if not png_path.exists():
                missing.append(png_path.name)
            continue
        rasterize_one(svg_path, png_path)
        print(f"  {svg_path.name} -> 24x24/{png_path.name}")

    if args.check:
        if missing:
            print(
                "missing PNG exports: " + ", ".join(missing),
                file=sys.stderr
            )
            return 1
        print(f"OK: {len(svgs)} icons have PNG exports")
        return 0

    print(f"Rasterized {len(svgs)} icon(s) to {PNG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
