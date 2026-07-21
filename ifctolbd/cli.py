from __future__ import annotations

import argparse
from pathlib import Path

from .config import ConversionProperties
from .converter import IFCtoLBDConverter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ifctolbd", description="Convert IFC STEP/IFCZIP to LBD RDF")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-uri", default="https://dot.dc.rwth-aachen.de/IFCtoLBDset#")
    parser.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--geometry", action="store_true")
    parser.add_argument("--geolocation", action="store_true")
    parser.add_argument("--units", action="store_true")
    parser.add_argument("--bounding-box-wkt", action="store_true")
    parser.add_argument("--no-properties", action="store_true")
    parser.add_argument("--no-ifcowl", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    props = ConversionProperties(
        has_building_properties=not args.no_properties,
        has_geometry=args.geometry,
        has_geolocation=args.geolocation,
        has_units=args.units,
        has_bounding_box_wkt=args.bounding_box_wkt,
        export_ifcowl=not args.no_ifcowl,
    )
    with IFCtoLBDConverter(args.base_uri, args.level) as converter:
        converter.convert_to_file(args.input, args.output, props)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

