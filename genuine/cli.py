"""Command-line entry points: ``genuine analyze <url|path>`` and ``genuine eval``.

``analyze`` runs the full deterministic pipeline offline. Handy for demos and for
exercising clone detection without the API (``--candidate`` points at local repos
to compare against, which is how the fixture-based flow works without the network).

``eval`` runs the labeled-corpus evaluation (Gate 7): it materializes every case
in the offline corpus, runs the real pipeline over it, and prints the detection +
triage metrics for one split — ``heldout`` by default, since that is the only
split whose numbers are ever reported (spec §8.4-6).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    a.add_argument("--explain", action="store_true",
                   help="Add a Groq LLM explanation + interview questions (advisory; needs GROQ_API_KEY)")

    e = sub.add_parser("eval", help="Run the labeled-corpus evaluation (Gate 7)")
    e.add_argument("--split", choices=["heldout", "tuning", "all"], default="heldout",
                   help="Which split to score (default: heldout — the only split whose "
                        "numbers are reported; tuning is where weights are tuned, §8.4-6)")
    e.add_argument("--out", metavar="PATH",
                   help="Also write the Markdown report to this file (UTF-8)")
    e.add_argument("--json", action="store_true",
                   help="Emit the metrics as JSON instead of the Markdown report")
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
            explain=args.explain,
        )
        if args.json:
            print(json.dumps(result.to_payload(), indent=2, default=str))
        else:
            print(result.report_text)
            if args.explain:
                _print_explanation(result)
        return 0

    if args.command == "eval":
        return _run_eval(args)
    return 1


def _run_eval(args) -> int:
    """Run the Gate-7 evaluation over one split and print/write the report.

    Imported lazily so the (offline, synthetic) corpus is only pulled in when
    someone actually asks for it — the common ``analyze`` path stays lean.
    ``main`` has already forced UTF-8 on stdout/stderr, so the report's ✓/—
    glyphs render on a Windows console; the ``--out`` file is written UTF-8 too.
    """
    from .eval import run_eval

    report = run_eval(args.split)
    if args.json:
        print(json.dumps(report.metrics_dict(), indent=2, default=str))
    else:
        print(report.to_markdown())
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.to_markdown(), encoding="utf-8")
        print(f"\nWrote evaluation artifact to {out_path}", file=sys.stderr)
    return 0


def _print_explanation(result) -> None:
    """Render the advisory LLM section (only called when --explain was passed)."""
    if result.ai_opinion is None and not result.interview_probes:
        hint = (
            "the Groq call returned nothing"
            if get_settings().has_llm
            else "no GROQ_API_KEY is configured"
        )
        print(
            f"\nAI EXPLANATION — unavailable ({hint}). "
            "The deterministic report above stands on its own."
        )
        return

    print("\n" + "=" * 70)
    print("AI EXPLANATION  (advisory only — does not affect the verdict)")
    print("=" * 70)
    if result.ai_opinion is not None:
        print(result.ai_opinion.summary)
    if result.interview_probes:
        print("\nInterview questions to verify authorship:")
        for i, probe in enumerate(result.interview_probes, 1):
            print(f"  {i}. {probe.question}  [{probe.targets_evidence_id}]")


if __name__ == "__main__":
    sys.exit(main())
