#!/usr/bin/env python3
"""Terminal entry point. No installation or third-party modules required."""
import sys
sys.dont_write_bytecode = True

import argparse
import json
import math

from devspace.report import render_text
from devspace.review import review_task


def integer_in_range(minimum, maximum):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("expected an integer") from None
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"expected {minimum}..{maximum}")
        return number
    return parse


def seconds(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected seconds") from None
    if not math.isfinite(number) or not 0 < number <= 3600:
        raise argparse.ArgumentTypeError("expected finite seconds in (0, 3600]")
    return number


def main():
    if sys.version_info < (3, 12):
        print("Python 3.12 or later is required.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Read-only metadata review of one selected task directory.")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="review a selected task; never deletes")
    review.add_argument("--task", required=True, help="selected task directory")
    review.add_argument("--json", action="store_true", help="print schema-versioned report as JSON")
    review.add_argument("--max-entries", type=integer_in_range(1, 100000), default=2000)
    review.add_argument("--max-depth", type=integer_in_range(1, 64), default=12)
    review.add_argument("--timeout", type=seconds, default=10.0)
    arguments = parser.parse_args()
    report = review_task(arguments.task, max_entries=arguments.max_entries,
                         max_depth=arguments.max_depth, timeout=arguments.timeout)
    print(json.dumps(report, ensure_ascii=True, indent=2) if arguments.json else render_text(report))
    if report["cancelled"]:
        return 130
    if report["invalid_scope"]:
        return 1
    return 0 if report["coverage"]["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
