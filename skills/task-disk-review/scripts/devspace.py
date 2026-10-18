#!/usr/bin/env python3
"""Terminal entry point. No installation or third-party modules required."""
import sys
sys.dont_write_bytecode = True

import argparse
import json
import math

from devspace.report import render_text, EVIDENCE_WARN_BYTES, EVIDENCE_EXPLAIN_BYTES
from devspace.plans import read_document, review_scope, write_manifest, write_plan


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
    parser = argparse.ArgumentParser(description="Read-only task/project/global inventory and assessed frozen review plans.")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="review a selected task; never deletes")
    scope = review.add_mutually_exclusive_group(required=True)
    scope.add_argument("--task", help="selected task directory")
    scope.add_argument("--project", help="selected Git or non-Git project; inventories linked worktrees")
    scope.add_argument("--global", dest="global_review", action="store_true", help="review configured development roots/providers")
    review.add_argument("--config", help="selected global configuration JSON; no implicit locations")
    review.add_argument("--assessment", help="agent-prepared contextual evidence JSON; never approval")
    review.add_argument("--manifest", help="optional historical helper-resource JSON")
    review.add_argument("--manifest-output", help="opt-in exclusive copy of the supplied helper-resource manifest")
    review.add_argument("--plan-output", help="new plan file outside reviewed roots; never overwrites")
    review.add_argument("--hold", action="append", default=[], help="exact held path; includes ancestors/descendants")
    review.add_argument("--exclude", action="append", default=[], help="path excluded from inspection/eligibility")
    review.add_argument("--json", action="store_true", help="print schema-versioned report as JSON")
    review.add_argument("--max-entries", type=integer_in_range(1, 100000), default=2000)
    review.add_argument("--max-depth", type=integer_in_range(1, 64), default=12)
    review.add_argument("--timeout", type=seconds, default=10.0)
    review.add_argument("--max-content-bytes", type=integer_in_range(1, 2**40), default=256 * 1024 * 1024)
    review.add_argument("--evidence-warn-bytes", type=integer_in_range(1, 2**40), default=EVIDENCE_WARN_BYTES, help="advisory logical packet size; strictly above warns")
    review.add_argument("--evidence-explain-bytes", type=integer_in_range(1, 2**40), default=EVIDENCE_EXPLAIN_BYTES, help="strictly above requests contextual explanation; never eligibility")
    arguments = parser.parse_args()
    try:
        assessment = read_document(arguments.assessment) if arguments.assessment else None
        manifest = read_document(arguments.manifest) if arguments.manifest else None
        if arguments.manifest_output and manifest is None:
            raise ValueError("manifest output requires explicitly supplied opted-in helper-resource records")
        if arguments.config and not arguments.global_review:
            raise ValueError("configuration is global-only")
        selected = read_document(arguments.config) if arguments.config else {"schema_version": 1, "roots": []}
        if not arguments.global_review:
            selected = arguments.task or arguments.project
        report = review_scope(selected, mode="global" if arguments.global_review else "task" if arguments.task else "project",
                              assessment=assessment, manifest=manifest, holds=arguments.hold, exclusions=arguments.exclude,
                              max_entries=arguments.max_entries, max_depth=arguments.max_depth, timeout=arguments.timeout,
                              max_content_bytes=arguments.max_content_bytes,
                              evidence_warn_bytes=arguments.evidence_warn_bytes, evidence_explain_bytes=arguments.evidence_explain_bytes)
        if arguments.plan_output:
            write_plan(arguments.plan_output, report["plan"])
        if arguments.manifest_output:
            write_manifest(arguments.manifest_output, manifest, report["scope_roots"])
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        print("Review input/output unavailable or invalid; no cleanup occurred. Narrow scope or check selected JSON/paths.", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True, indent=2) if arguments.json else render_text(report))
    if report["cancelled"]:
        return 130
    if report["invalid_scope"]:
        return 1
    return 0 if report["coverage"]["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
