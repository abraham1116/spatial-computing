"""Numbers the site prints must match reality: a stale count was shipped twice."""
import re
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


def test_site_test_count_matches_the_collected_total():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "tests"],
                         capture_output=True, text=True, cwd=SITE.parent).stdout
    collected = int(re.search(r"(\d+) tests? collected", out).group(1))
    sys.path.insert(0, str(SITE))
    try:
        import scaffold
    finally:
        sys.path.remove(str(SITE))
    assert scaffold.TEST_COUNT == collected, f"site/scaffold.py says {scaffold.TEST_COUNT}, pytest collects {collected}: update TEST_COUNT"


def test_docs_index_has_no_hardcoded_version_or_count():
    for f in ("content_en.py", "content_fr.py"):
        src = (SITE / f).read_text()
        assert "@@V@@" in src and "@@N@@" in src, f"{f}: status callout must use the placeholders"
        assert not re.search(r"Version 0\.\d+\.\d+\.", src), f"{f}: hardcoded version in the status callout"
