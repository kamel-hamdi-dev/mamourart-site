"""The Actions report states the result and keeps external failures non-blocking."""

import os
import subprocess
import sys
import textwrap

from tests.checks import ROOT

SCRIPT = ROOT / ".github" / "scripts" / "pytest_summary.py"

FAILURE = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="utf-8"?>
    <testsuites>
      <testsuite name="pytest" tests="1" failures="1" errors="0" skipped="0">
        <testcase classname="tests.test_external_links" name="test_external_links_respond" time="1.5">
          <failure message="external links failed: https://www.linkedin.com/in/kamel-hamdi-dev/ -&gt; 403">trace</failure>
          <system-out>https://www.linkedin.com/in/kamel-hamdi-dev/ -&gt; 403</system-out>
        </testcase>
      </testsuite>
    </testsuites>
    """
)

SUCCESS = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="utf-8"?>
    <testsuites>
      <testsuite name="pytest" tests="1" failures="0" errors="0" skipped="0">
        <testcase classname="tests.test_files" name="test_homepage_document" time="0.02" />
      </testsuite>
    </testsuites>
    """
)


def test_required_success_mentions_the_check_name(tmp_path):
    markdown, result, summary = _publish(tmp_path, SUCCESS, mode="required", title="Contrôles obligatoires du site")
    assert result.returncode == 0, result.stderr
    assert "**Succès.**" in markdown
    assert "Python site checks" in markdown
    assert "tests.test_files::test_homepage_document" in markdown
    assert "| Réussis | 1 |" in markdown
    assert summary.read_text(encoding="utf-8") == markdown


def test_required_failure_exits_nonzero(tmp_path):
    markdown, result, _summary = _publish(tmp_path, FAILURE, mode="required", title="Contrôles obligatoires du site")
    assert result.returncode == 1
    assert "**Échec.**" in markdown
    assert "Python site checks" in markdown
    assert "test_external_links_respond" in markdown


def test_optional_failure_stays_successful_and_warns(tmp_path):
    markdown, result, summary = _publish(tmp_path, FAILURE, mode="optional", title="Liens externes")
    assert result.returncode == 0, result.stderr
    assert "Rapport informatif" in markdown
    assert "panne Internet ou LinkedIn" in markdown
    assert "linkedin.com" in markdown
    assert "::warning title=Liens externes::" in result.stdout
    assert summary.read_text(encoding="utf-8") == markdown


def test_optional_report_lists_each_external_link(tmp_path):
    xml = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="1" failures="0" errors="0" skipped="0">
            <testcase classname="tests.test_external_links" name="test_external_links_respond" time="2.2">
              <system-out>--------------------------------- Captured Out ---------------------------------
        https://github.com/kamel-hamdi-dev -&gt; 200
        https://www.linkedin.com/in/kamel-hamdi-dev/ -&gt; 999
        https://www.mamourart.com/ -&gt; 200
              </system-out>
            </testcase>
          </testsuite>
        </testsuites>
        """
    )
    markdown, result, _summary = _publish(tmp_path, xml, mode="optional", title="Liens externes")
    assert result.returncode == 0, result.stderr
    assert "Captured Out" not in markdown
    assert "| `https://github.com/kamel-hamdi-dev` | 200 |" in markdown
    assert "| `https://www.linkedin.com/in/kamel-hamdi-dev/` | 999 (réponse automatique LinkedIn) |" in markdown
    assert "| `https://www.mamourart.com/` | 200 |" in markdown


def test_optional_missing_report_does_not_fail(tmp_path):
    markdown = tmp_path / "summary.md"
    result = _run(tmp_path / "missing.xml", markdown, tmp_path / "step.md", mode="optional", title="Liens externes")
    assert result.returncode == 0, result.stderr
    text = markdown.read_text(encoding="utf-8")
    assert "Rapport incomplet" in text
    assert "informatif" in text


def test_required_missing_report_fails(tmp_path):
    markdown = tmp_path / "summary.md"
    result = _run(
        tmp_path / "missing.xml",
        markdown,
        tmp_path / "step.md",
        mode="required",
        title="Contrôles obligatoires du site",
    )
    assert result.returncode == 1
    assert "Échec" in markdown.read_text(encoding="utf-8")


def _publish(tmp_path, xml: str, *, mode: str, title: str):
    junit = tmp_path / "junit.xml"
    junit.write_text(xml, encoding="utf-8")
    markdown = tmp_path / "summary.md"
    summary = tmp_path / "step.md"
    result = _run(junit, markdown, summary, mode=mode, title=title)
    return markdown.read_text(encoding="utf-8"), result, summary


def _run(junit, markdown, summary, *, mode: str, title: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GITHUB_ACTIONS"] = "true"
    env["GITHUB_STEP_SUMMARY"] = str(summary)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(junit),
            "--title",
            title,
            "--mode",
            mode,
            "--markdown",
            str(markdown),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
