#!/usr/bin/env python3
"""Write a readable pytest report for the GitHub Actions job summary."""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_CAPTURED = re.compile(r"^-+\s+Captured\s+.*\s+-+$")
_LINK = re.compile(r"^(https://\S+)\s+->\s+(.+)$")

STATUS_PASSED = "réussi"
STATUS_FAILED = "échec"
STATUS_ERROR = "erreur"
STATUS_SKIPPED = "ignoré"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--mode", choices=("required", "optional"), required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args(argv)

    cases, problem = _load_cases(args.junit)
    markdown, exit_code, annotations = _render(args.title, args.mode, cases, problem)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    _append_step_summary(markdown)
    for level, message in annotations:
        _annotate(level, message)
    return exit_code


def _load_cases(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.is_file():
        return [], f"Fichier JUnit introuvable : {path}"
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        return [], f"Fichier JUnit illisible : {error}"
    cases = [_case(node) for node in root.findall(".//testcase")]
    return cases, ""


def _case(node: ET.Element) -> dict[str, str]:
    classname = node.get("classname", "").strip()
    name = node.get("name", "").strip()
    label = f"{classname}::{name}" if classname else name
    failure = node.find("failure")
    error = node.find("error")
    skipped = node.find("skipped")
    if error is not None:
        status = STATUS_ERROR
        detail = _detail(error)
    elif failure is not None:
        status = STATUS_FAILED
        detail = _detail(failure)
    elif skipped is not None:
        status = STATUS_SKIPPED
        detail = _detail(skipped)
    else:
        status = STATUS_PASSED
        detail = ""
    lines = _clean_lines(detail)
    for line in _clean_lines(_text(node.find("system-out"))):
        if line not in lines:
            lines.append(line)
    return {
        "label": label or "(test sans nom)",
        "status": status,
        "time": _seconds(node.get("time", "")),
        "detail": "\n".join(lines),
    }


def _detail(node: ET.Element) -> str:
    message = node.get("message", "")
    body = _text(node)
    return message or body


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _seconds(raw: str) -> str:
    try:
        return f"{float(raw):.2f} s"
    except ValueError:
        return raw or "—"


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line or _CAPTURED.fullmatch(line):
            continue
        lines.append(_clip(line, 300))
    return lines


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _render(
    title: str,
    mode: str,
    cases: list[dict[str, str]],
    problem: str,
) -> tuple[str, int, list[tuple[str, str]]]:
    failures = sum(case["status"] == STATUS_FAILED for case in cases)
    errors = sum(case["status"] == STATUS_ERROR for case in cases)
    skipped = sum(case["status"] == STATUS_SKIPPED for case in cases)
    passed = sum(case["status"] == STATUS_PASSED for case in cases)
    total = len(cases)
    verdict, exit_code = _verdict(
        mode=mode,
        total=total,
        failures=failures,
        errors=errors,
        problem=problem,
    )
    level = "error" if mode == "required" else "warning"

    lines = [
        f"## {title}",
        "",
        verdict,
        "",
        "| | |",
        "| --- | ---: |",
        f"| Réussis | {passed} |",
        f"| Échecs | {failures} |",
        f"| Erreurs | {errors} |",
        f"| Ignorés | {skipped} |",
        f"| Total | {total} |",
        "",
    ]
    if problem:
        lines.extend([problem, ""])
    if cases:
        lines.extend(
            [
                "| Résultat | Test | Durée |",
                "| --- | --- | ---: |",
            ]
        )
        for case in cases:
            label = case["label"].replace("|", "\\|")
            lines.append(f"| {case['status']} | `{label}` | {case['time']} |")
        lines.append("")
    link_rows, notes = _split_details(cases)
    if link_rows:
        lines.extend(["| Lien | Réponse |", "| --- | --- |"])
        for url, status in link_rows:
            shown = status
            if status == "999" and "linkedin.com" in url:
                shown = "999 (réponse automatique LinkedIn)"
            lines.append(f"| `{url}` | {shown.replace('|', '\\|')} |")
        lines.append("")
    if notes:
        lines.append("### Détails")
        lines.append("")
        for label, note in notes:
            lines.append(f"- `{label}` : {note}")
        lines.append("")

    annotations = []
    if problem:
        annotations.append((level, f"{title} : {problem}"))
    for case in cases:
        if case["status"] in (STATUS_FAILED, STATUS_ERROR):
            message = f"{title} : {case['label']} ({case['status']})"
            if case["detail"]:
                message = f"{message} — {' '.join(case['detail'].split())}"
            annotations.append((level, _clip(message, 700)))
    return "\n".join(lines).rstrip() + "\n", exit_code, annotations


def _split_details(cases: list[dict[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    links: list[tuple[str, str]] = []
    notes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for case in cases:
        for line in case["detail"].splitlines():
            match = _LINK.fullmatch(line)
            if match is None:
                notes.append((case["label"], line))
                continue
            url = match.group(1)
            if url in seen:
                continue
            seen.add(url)
            links.append((url, match.group(2)))
    return links, notes


def _verdict(*, mode: str, total: int, failures: int, errors: int, problem: str) -> tuple[str, int]:
    broken = bool(problem) or failures + errors > 0 or total == 0
    if mode == "required":
        if problem or total == 0:
            return "**Échec.** Aucun contrôle obligatoire exploitable dans le rapport.", 1
        if failures or errors:
            return "**Échec.** Contrôle obligatoire : Python site checks.", 1
        return "**Succès.** Contrôle obligatoire : Python site checks.", 0
    if problem or total == 0:
        return "**Rapport incomplet.** Liens externes, à titre informatif.", 0
    if broken:
        return (
            "**Liens externes en échec.** Rapport informatif : une panne Internet ou LinkedIn laisse passer la pull request.",
            0,
        )
    return "**Succès.** Rapport informatif des liens externes.", 0


def _append_step_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(markdown)
        if not markdown.endswith("\n"):
            handle.write("\n")


def _annotate(level: str, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    clean = " ".join(message.split())
    for old, new in (("%", "%25"), ("\r", "%0D"), ("\n", "%0A")):
        clean = clean.replace(old, new)
    title = "Contrôle obligatoire" if level == "error" else "Liens externes"
    print(f"::{level} title={title}::{clean}")


if __name__ == "__main__":
    sys.exit(main())
