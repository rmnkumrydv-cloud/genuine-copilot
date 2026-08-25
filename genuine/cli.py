"""Command-line entry point: ``genuine analyze <url|path>``.

Runs the full deterministic pipeline offline. Handy for demos and for exercising
clone detection without the API (``--candidate`` points at local repos to compare
against, which is how the fixture-based flow works without the network).
"""

from __future__ import annotations

import argparse
import json
import sys

from .candidates import candidate_from_path
from .config import get_settings
from .pipeline import analyze


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genuine", description="Neuro-symbolic repo authenticity checker")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Analyze a repo URL or local path")
    a.add_argument("target", help="GitHub URL or local directory path")
    a.add_argument("--candidate", action="append", default=[], metavar="PATH",
                   help="Local repo to compare against (repeatable)")
    a.add_argument("--json", action="store_true", help="Emit the full JSON payload")
    a.add_argument("--top-k", type=int, default=40, help="How many significant files to deep-compare")
    a.add_argument("--no-register", action="store_true", help="Don't add this repo to the registry")
    return p


def main(argv: list[str] | None = None) -> int:
    # The report uses typographic dashes; Windows consoles and redirected pipes
    # often default to a non-UTF-8 locale encoding that can't represent them.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    args = _build_parser().parse_args(argv)
    settings = get_settings()

    if args.command == "analyze":
        candidates = [candidate_from_path(c) for c in args.candidate]
        result = analyze(
            args.target,
            db_path=settings.db_file,
            cache_root=settings.clone_dir,
            candidates=candidates,
            token=settings.github_token,
            register_in_registry=not args.no_register,
            top_k=args.top_k,
        )
        if args.json:
            print(json.dumps(result.to_payload(), indent=2, default=str))
        else:
            print(result.report_text)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
