"""Command line: python -m preflight <file> --product business-card [--json]"""

from __future__ import annotations

import argparse
import json
import sys

from .report import check_file
from .specs import all_products


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preflight", description="Check print artwork for a product.")
    parser.add_argument("file", nargs="?", help="PDF, PNG or JPG")
    parser.add_argument("--product", default="business-card", help="product id (see --list)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--list", action="store_true", help="list products and exit")
    args = parser.parse_args(argv)

    if args.list:
        for p in all_products():
            print(f"{p.id:16} {p.name}")
        return 0
    if not args.file:
        parser.error("a file is required")

    report = check_file(args.file, args.product)
    print(json.dumps(report.to_dict(), indent=2) if args.json else report.to_markdown())
    return {"pass": 0, "warn": 0, "fail": 1}[report.verdict]


if __name__ == "__main__":
    sys.exit(main())
