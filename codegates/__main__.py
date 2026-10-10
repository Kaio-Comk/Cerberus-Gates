"""CLI: python -m codegates PATH [--check NAME ...] [--skip DIR ...]. Exit 1 on findings."""
from __future__ import annotations

import argparse
import sys

from .checks import CHECKS, DEFAULT_SKIP, scan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="codegates", description=__doc__)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--check", action="append", choices=sorted(CHECKS),
                    help="run only this check (repeatable); default: all")
    ap.add_argument("--skip", action="append", default=[],
                    help="extra directory name to skip (repeatable)")
    args = ap.parse_args(argv)
    findings = scan(args.path, args.check, set(DEFAULT_SKIP) | set(args.skip))
    for f in findings:
        print(f)
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
