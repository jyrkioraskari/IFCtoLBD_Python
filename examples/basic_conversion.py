#!/usr/bin/env python3
"""Convert an IFC model to Linked Building Data using native Python."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow direct execution from a source checkout before the package is installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ifctolbd import IFCtoLBDConverter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ifc_file",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "data" / "two_walls.ifc",
        help="IFC or IFCZIP input (defaults to the bundled two-wall model)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("two_walls.ttl"),
        help="Turtle output path (default: two_walls.ttl)",
    )
    args = parser.parse_args()

    with IFCtoLBDConverter("https://example.org/building#", level=3) as converter:
        graph = converter.convert_to_file(args.ifc_file, args.output)

    print(f"Converted {args.ifc_file} to {args.output} ({len(graph)} triples)")


if __name__ == "__main__":
    main()
