"""Ingestion tests: exclusion rules, significance ranking, coverage, fingerprint
— exercised against a real temp git repo (spec §8.1, Gate 1)."""

from __future__ import annotations

from genuine.ingestion import ingest_local
from genuine.ingestion.languages import classify_exclusion, count_loc, detect_language


def test_exclusion_rules():
    assert classify_exclusion("node_modules/left-pad/index.js") == "vendor"
    assert classify_exclusion("src/app.py") == ""
    assert classify_exclusion("tests/test_app.py") == "test"
    assert classify_exclusion("package-lock.json") == "lockfile"
    assert classify_exclusion("static/app.min.js") == "generated"
    assert classify_exclusion("logo.png") == "non_code"
    assert classify_exclusion("api/pb/service.pb.go") == "generated"


def test_language_detection():
    assert detect_language("a/b/c.py") == "python"
    assert detect_language("x.tsx") == "typescript"
    assert detect_language("Makefile") == "unknown"


def test_count_loc_ignores_blank_lines():
    assert count_loc("a\n\n\nb\n   \nc\n") == 3


def test_ingest_ranks_and_excludes(make_git_repo):
    core = "import helper\n\n" + "\n".join(f"def f{i}():\n    return helper.g({i})" for i in range(10))
    helper = "\n".join(f"def g{i}(x):\n    return x + {i}" for i in range(20))
    repo = make_git_repo(
        "ranked",
        [
            {
                "message": "initial",
                "files": {
                    "core.py": core,
                    "helper.py": helper,
                    "node_modules/dep/index.js": "module.exports = 42\n",
                    "tests/test_core.py": "def test_x():\n    assert True\n",
                    "yarn.lock": "# lock\n",
                },
                "date": "2023-01-01 12:00:00 +0000",
            }
        ],
    )
    analysis = ingest_local(repo)

    by_path = {f.path: f for f in analysis.files}
    assert by_path["node_modules/dep/index.js"].excluded
    assert by_path["tests/test_core.py"].exclude_reason == "test"
    assert by_path["yarn.lock"].exclude_reason == "lockfile"

    # helper.py is imported by core.py → positive centrality, should be ranked.
    assert by_path["helper.py"].significance_rank > 0
    assert by_path["helper.py"].import_centrality > 0
    assert by_path["core.py"].import_centrality == 0.0  # nothing imports core

    # coverage: only non-excluded python files count toward total.
    assert 0 < analysis.coverage_ratio <= 1.0
    assert analysis.total_loc > 0
    assert analysis.fingerprint  # MinHash signature present
    assert len(analysis.commits) == 1


def test_ingest_plain_dir_without_git(tmp_path):
    (tmp_path / "solo.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    analysis = ingest_local(tmp_path)
    assert analysis.commits == []  # no git history, still analyzable
    assert any(f.path == "solo.py" for f in analysis.files)
