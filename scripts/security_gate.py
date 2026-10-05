#!/usr/bin/env python3
"""Security gate : lit les rapports des scanners et applique la politique de blocage.

Politique :
    CRITICAL -> pipeline bloque
    HIGH     -> pipeline bloque
    MEDIUM   -> avertissement
    LOW      -> information

Usage : python3 scripts/security_gate.py <rapport.json> [<rapport.json> ...]
Le type de rapport est deduit du nom du fichier (gitleaks*, semgrep*, trivy*).
Un rapport manquant ou illisible bloque le pipeline (fail closed).
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
POLICY = {
    "CRITICAL": "bloquant",
    "HIGH": "bloquant",
    "MEDIUM": "avertissement",
    "LOW": "information",
}
BLOCKING = {"CRITICAL", "HIGH"}
SEMGREP_SEVERITY = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}


def normalize(severity):
    severity = (severity or "").upper()
    return severity if severity in SEVERITIES else "LOW"


def parse_gitleaks(data):
    # Tout secret detecte est considere comme critique
    for leak in data or []:
        yield "CRITICAL", f"{leak.get('RuleID')} dans {leak.get('File')}:{leak.get('StartLine')}"


def parse_semgrep(data):
    for result in data.get("results", []):
        severity = SEMGREP_SEVERITY.get(result.get("extra", {}).get("severity"), "LOW")
        location = f"{result.get('path')}:{result.get('start', {}).get('line')}"
        yield severity, f"{result.get('check_id', '').split('.')[-1]} dans {location}"


def parse_trivy(data):
    for result in data.get("Results") or []:
        target = result.get("Target", "")
        for vuln in result.get("Vulnerabilities") or []:
            fixed = vuln.get("FixedVersion") or "pas de correctif"
            yield (
                normalize(vuln.get("Severity")),
                (
                    f"{vuln.get('VulnerabilityID')} {vuln.get('PkgName')} "
                    f"{vuln.get('InstalledVersion')} -> {fixed} ({target})"
                ),
            )
        for misconf in result.get("Misconfigurations") or []:
            if misconf.get("Status", "FAIL") == "FAIL":
                yield (
                    normalize(misconf.get("Severity")),
                    (f"{misconf.get('ID')} {misconf.get('Title')} ({target})"),
                )
        for secret in result.get("Secrets") or []:
            yield "CRITICAL", f"secret {secret.get('RuleID')} ({target})"


PARSERS = {"gitleaks": parse_gitleaks, "semgrep": parse_semgrep, "trivy": parse_trivy}


def main(paths):
    findings = []  # (outil, severite, description)
    errors = []

    for path in map(Path, paths):
        tool = next((name for name in PARSERS if path.name.startswith(name)), None)
        if tool is None:
            errors.append(f"{path.name} : type de rapport inconnu")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "null")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name} : rapport absent ou illisible ({exc.__class__.__name__})")
            continue
        for severity, description in PARSERS[tool](data):
            findings.append((path.stem, severity, description))

    counts = Counter((source, severity) for source, severity, _ in findings)
    sources = [Path(p).stem for p in paths]
    blocking = [f for f in findings if f[1] in BLOCKING]
    warnings = [f for f in findings if f[1] == "MEDIUM"]
    passed = not blocking and not errors

    lines = ["## Security gate : " + ("PASS" if passed else "FAIL"), ""]
    lines.append("| Rapport | " + " | ".join(SEVERITIES) + " |")
    lines.append("|---|" + "---|" * len(SEVERITIES))
    for source in sources:
        cells = " | ".join(str(counts.get((source, s), 0)) for s in SEVERITIES)
        lines.append(f"| {source} | {cells} |")
    lines.append("")
    lines.append("Politique : " + ", ".join(f"{s} = {POLICY[s]}" for s in SEVERITIES) + ".")
    if errors:
        lines += ["", "### Erreurs (bloquantes)", *[f"- {e}" for e in errors]]
    if blocking:
        lines += ["", "### Problemes bloquants"]
        lines += [f"- **{sev}** [{src}] {desc}" for src, sev, desc in blocking[:50]]
        if len(blocking) > 50:
            lines.append(f"- ... et {len(blocking) - 50} autres (voir les rapports en artefacts)")
    if warnings:
        lines += ["", "### Avertissements (non bloquants)"]
        lines += [f"- [{src}] {desc}" for src, _, desc in warnings[:30]]

    report = "\n".join(lines)
    print(report)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")

    # Annotations visibles directement dans l'interface GitHub Actions
    if os.environ.get("GITHUB_ACTIONS"):
        for src, sev, desc in blocking[:20]:
            print(f"::error title=Security gate {sev}::[{src}] {desc}")
        for src, _, desc in warnings[:20]:
            print(f"::warning title=Security gate MEDIUM::[{src}] {desc}")

    return 0 if passed else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
