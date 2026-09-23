"""RQ4 static analysis for potential static security modifications.

Potential static security modification is an independent static-analysis
dimension. It is derived from ``configs/security_rules.yaml`` matches against
added patch lines, not from taxonomy families such as guardrail, policy, or
script.

Outputs (eval/tables-and-figures/): 15 ``rq4-security-*.csv`` tables.

Usage:
    uv run python -m eval.label.rq4
    uv run python -m eval.label.rq4 --num_samples 50 --out-dir DIR
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

import yaml

from eval.label import utils

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSTANCES = ROOT / "data" / "analysis" / "instances.jsonl"
DEFAULT_RULES = ROOT / "configs" / "security_rules.yaml"
DEFAULT_OUT_DIR = ROOT / "eval" / "tables-and-figures"
SEVERITY_RANK = {"": 0, "WARNING": 1, "CRITICAL": 2}
RULE_PREFILTER_PATTERNS = {
    "NET001": [
        r"\bcurl\b",
        r"\bwget\b",
        r"requests\.",
        r"urllib\.",
        r"httpx\.",
        r"fetch\(",
    ],
    "NET002": [r"\bcurl\b", r"\bwget\b", r"nc\s+", r"netcat"],
    "FILE001": [
        r"\.ssh",
        r"\.env",
        r"\.aws",
        r"\.azure",
        r"\.credentials",
        r"\.pem",
        r"\.key",
        r"id_rsa",
        r"id_ed25519",
        r"credentials\.json",
        r"secrets\.",
        r"password",
        r"token",
        r"api[_-]?key",
    ],
    "FILE002": [
        r"\brm\b",
        r"\bchmod\b",
        r"\bdd\b",
        r">\s*/(?:etc|usr|bin|sbin)/",
    ],
    "CMD001": [
        r"\bsudo\b",
        r"\bsu\s",
        r"\brm\b",
        r"\bchmod\b",
        r"\bdd\b",
        r":>",
    ],
    "CMD002": [r"os\.system", r"subprocess\.", r"\bexec\s*\(", r"popen\s*\("],
    "INJ001": [r"inject", r"prepend", r"insert"],
    "INJ002": [r"\beval\s*\(", r"\bexec\s*\(", r"__import__", r"\bcompile\s*\("],
    "INJ003": [r"\bbash\b", r"/dev/tcp", r"\bnc\b", r"netcat", r"prod"],
    "DEP001": [r"\bpip\b", r"npm", r"\byarn\b", r"\bgem\b"],
    "DEP002": [
        r"==",
        r"--upgrade",
        r"--force-reinstall",
        r"--ignore-installed",
        r"force",
    ],
    "OBF001": [r"base64", r"\bchr\s*\(", r"\bexec\s*\(", r"decode"],
    "OBF002": [r"__import__", r"getattr", r"vars\("],
}
GLOBAL_PREFILTER_TEXTS = [
    ".aws",
    ".azure",
    ".credentials",
    ".env",
    ".key",
    ".pem",
    ".ssh",
    "--force-reinstall",
    "--ignore-installed",
    "--upgrade",
    "/bin/",
    "/dev/tcp",
    "/etc/",
    "/sbin/",
    "/usr/",
    ":>",
    "==",
    "__import__",
    "api-key",
    "api_key",
    "apikey",
    "base64",
    "bash",
    "chmod",
    "chr",
    "compile",
    "credentials.json",
    "curl",
    "dd ",
    "dd\t",
    " dd",
    "decode",
    "eval",
    "exec",
    "fetch(",
    "force",
    "gem",
    "getattr",
    "httpx.",
    "id_ed25519",
    "id_rsa",
    "inject",
    "insert",
    "nc ",
    "nc\t",
    " nc",
    "netcat",
    "npm",
    "os.system",
    "password",
    "pip",
    "pnpm",
    "popen",
    "prepend",
    "prod",
    "requests.",
    "rm ",
    "rm\t",
    " rm",
    "secrets.",
    "subprocess.",
    "su ",
    "su\t",
    " su",
    "sudo",
    "token",
    "urllib.",
    "vars",
    "wget",
    "yarn",
]
INSTANCE_FIELDNAMES = [
    "instance_id",
    "upstream",
    "fork_owner",
    "branch",
    "has_potential_security_implication",
    "max_severity",
    "matched_rule_ids",
    "matched_rule_names",
    "matched_categories",
    "matched_files",
    "match_count",
]
MATCH_FIELDNAMES = [
    "instance_id",
    "upstream",
    "fork_owner",
    "branch",
    "path",
    "file_status",
    "patch_line",
    "category",
    "rule_id",
    "rule_name",
    "severity",
    "snippet",
]
CONTEXT_MATCH_FIELDNAMES = [
    "instance_id",
    "upstream",
    "fork_owner",
    "branch",
    "path",
    "file_status",
    "patch_line",
    "line_role",
    "category",
    "rule_id",
    "rule_name",
    "severity",
    "snippet",
]
DELETED_LINE_ONLY_MATCH_FIELDNAMES = [
    "instance_id",
    "upstream",
    "fork_owner",
    "branch",
    "path",
    "file_status",
    "changed_block",
    "patch_line",
    "line_role",
    "category",
    "rule_id",
    "rule_name",
    "severity",
    "snippet",
]
HUNK_FIELDNAMES = [
    "instance_id",
    "upstream",
    "fork_owner",
    "branch",
    "path",
    "file_status",
    "changed_block",
    "hunk_status",
    "has_added_line_match",
    "has_removed_line_match",
    "has_context_line_match",
    "max_severity",
    "matched_rule_ids",
    "matched_rule_names",
    "matched_categories",
    "added_line_match_count",
    "removed_line_match_count",
    "context_line_match_count",
    "match_count",
]
HUNK_STATUS_FIELDNAMES = [
    "hunk_status",
    "branches",
    "branch_prevalence",
]
ADDED_LINE_PATTERN_FIELDNAMES = [
    "pattern_name",
    "rule_id",
    "severity",
    "category",
    "instances",
    "branch_prevalence",
    "match_count",
    "match_share",
]
LINE_EDIT_SPLIT_FIELDNAMES = [
    "edit_type",
    "instances",
    "branch_prevalence",
    "edit_share",
]
SUMMARY_FIELDNAMES = [
    "analyzed_branches",
    "branches_with_security_implication",
    "security_prevalence",
    "critical_branches",
    "critical_prevalence",
    "warning_branches",
    "warning_prevalence",
    "match_count",
]
CATEGORY_FIELDNAMES = [
    "category",
    "branches",
    "branch_prevalence",
    "match_count",
]
ORIGIN_SUMMARY_FIELDNAMES = [
    "analyzed_branches",
    "added_line_match_branches",
    "added_line_match_prevalence",
    "context_line_match_branches",
    "context_line_match_prevalence",
    "both_added_line_and_context_branches",
    "added_line_only_branches",
    "context_only_edit_branches",
    "context_only_edit_prevalence",
    "deleted_line_only_match_branches",
    "deleted_line_only_match_prevalence",
    "added_line_match_count",
    "context_line_match_count",
    "deleted_line_only_match_count",
]
ORIGIN_CATEGORY_FIELDNAMES = [
    "category",
    "added_line_match_branches",
    "added_line_match_prevalence",
    "context_line_match_branches",
    "context_line_match_prevalence",
    "context_only_edit_branches",
    "context_only_edit_prevalence",
    "added_line_match_count",
    "context_line_match_count",
]
ORIGIN_PATTERN_FIELDNAMES = [
    "pattern_name",
    "rule_id",
    "severity",
    "added_line_match_branches",
    "added_line_match_prevalence",
    "context_line_match_branches",
    "context_line_match_prevalence",
    "context_only_edit_branches",
    "context_only_edit_prevalence",
    "added_line_match_count",
    "context_line_match_count",
]
STATUS_FIELDNAMES = [
    "file_status",
    "instances",
    "branch_prevalence",
]


def rule_category(section: str) -> str:
    """Return a short category name from a security-rule YAML section."""
    return section.removesuffix("_rules")


def load_security_rules(path: str | Path = DEFAULT_RULES) -> list[dict[str, Any]]:
    """Load security rules and compile their regex patterns."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    rules = []
    for section, entries in data.items():
        if not section.endswith("_rules"):
            continue
        for entry in entries or []:
            pattern_texts = entry.get("patterns", [])
            patterns = [
                re.compile(pattern, re.IGNORECASE)
                for pattern in pattern_texts
            ]
            combined_pattern = (
                re.compile(
                    "|".join(f"(?:{pattern})" for pattern in pattern_texts),
                    re.IGNORECASE,
                )
                if pattern_texts
                else None
            )
            prefilter_patterns = RULE_PREFILTER_PATTERNS.get(entry["id"], [])
            prefilter_pattern = (
                re.compile(
                    "|".join(
                        pattern
                        for pattern in sorted(
                            prefilter_patterns,
                            key=len,
                            reverse=True,
                        )
                    ),
                    re.IGNORECASE,
                )
                if prefilter_patterns
                else None
            )
            rules.append(
                {
                    "category": rule_category(section),
                    "id": entry["id"],
                    "name": entry["name"],
                    "severity": entry["severity"],
                    "description": entry.get("description", ""),
                    "allowed_domains": entry.get("allowed_domains", []),
                    "patterns": patterns,
                    "combined_pattern": combined_pattern,
                    "prefilter_patterns": prefilter_patterns,
                    "prefilter_pattern": prefilter_pattern,
                }
            )
    return rules


def diff_content_lines(
    diff: str,
    roles: set[str] | None = None,
) -> list[tuple[int, str, str]]:
    """Return ``(patch_line_number, role, content)`` from unified-diff content."""
    return [
        (line_number, role, content)
        for line_number, _, role, content in diff_changed_block_lines(diff, roles)
    ]


def diff_changed_block_lines(
    diff: str,
    roles: set[str] | None = None,
) -> list[tuple[int, int, str, str]]:
    """Return ``(patch_line_number, block_id, role, content)`` from a diff."""
    lines = []
    block_id = 0
    seen_block = False
    for line_number, line in enumerate(diff.splitlines(), start=1):
        if line.startswith("@@"):
            if seen_block:
                block_id += 1
            seen_block = True
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            role = "added"
        elif line.startswith("-"):
            role = "removed"
        elif line.startswith(" "):
            role = "context"
        else:
            continue
        if roles is not None and role not in roles:
            continue
        lines.append((line_number, block_id, role, line[1:]))
    return lines


def classify_hunk_status(roles: set[str]) -> str:
    """Return the changed-line status of a unified-diff hunk."""
    changed_roles = roles & {"added", "removed"}
    if changed_roles == {"added", "removed"}:
        return "modified"
    if changed_roles == {"added"}:
        return "added"
    if changed_roles == {"removed"}:
        return "removed"
    return "context"


def diff_hunks(diff: str) -> list[dict[str, Any]]:
    """Return unified-diff hunks with changed-line status metadata."""
    hunks = []
    current: dict[str, Any] | None = None
    block_id = -1
    for line_number, line in enumerate(diff.splitlines(), start=1):
        if line.startswith("@@"):
            block_id += 1
            current = {
                "changed_block": block_id,
                "header": line,
                "lines": [],
            }
            hunks.append(current)
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            role = "added"
        elif line.startswith("-"):
            role = "removed"
        elif line.startswith(" "):
            role = "context"
        else:
            continue
        if current is None:
            block_id += 1
            current = {
                "changed_block": block_id,
                "header": "",
                "lines": [],
            }
            hunks.append(current)
        current["lines"].append(
            {
                "patch_line": line_number,
                "role": role,
                "content": line[1:],
            }
        )
    for hunk in hunks:
        roles = {line["role"] for line in hunk["lines"]}
        hunk["hunk_status"] = classify_hunk_status(roles)
    return hunks


def added_lines(diff: str) -> list[tuple[int, str]]:
    """Return ``(patch_line_number, added_content)`` from a unified diff."""
    return [
        (line_number, content)
        for line_number, _, content in diff_content_lines(diff, roles={"added"})
    ]


def is_allowed_network_line(line: str, rule: dict[str, Any]) -> bool:
    """Return whether a NET001 line targets an explicitly allowed domain."""
    allowed_domains = rule.get("allowed_domains") or []
    if rule["id"] != "NET001" or not allowed_domains:
        return False
    lower = line.lower()
    return any(domain.lower() in lower for domain in allowed_domains)


def rule_matches_line(line: str, rule: dict[str, Any]) -> bool:
    """Return whether a rule matches one added line."""
    if is_allowed_network_line(line, rule):
        return False
    prefilter_pattern = rule.get("prefilter_pattern")
    if prefilter_pattern is not None and not prefilter_pattern.search(line):
        return False
    combined_pattern = rule.get("combined_pattern")
    if combined_pattern is not None:
        return bool(combined_pattern.search(line))
    return any(pattern.search(line) for pattern in rule["patterns"])


def matching_rules_for_line(
    line: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return security rules matching one diff line."""
    lower = line.lower()
    if not any(text in lower for text in GLOBAL_PREFILTER_TEXTS):
        return []
    return [rule for rule in rules if rule_matches_line(line, rule)]


def redact_snippet(snippet: str) -> str:
    """Redact common secret-bearing assignment values in a snippet."""

    def is_secret_key(key: str) -> bool:
        return bool(re.search(r"api[_-]?key|token|password|secret", key, re.IGNORECASE))

    def replace_quoted(match: re.Match) -> str:
        if not is_secret_key(match.group(1)):
            return match.group(0)
        return f"{match.group(1)}={match.group(2)}<redacted>{match.group(2)}"

    def replace_unquoted(match: re.Match) -> str:
        if not is_secret_key(match.group(1)):
            return match.group(0)
        return f"{match.group(1)}=<redacted>"

    def replace_key_value(match: re.Match) -> str:
        if not is_secret_key(match.group(2)):
            return match.group(0)
        return (
            f"{match.group(1)}{match.group(2)}{match.group(1)}: "
            f"{match.group(3)}<redacted>{match.group(3)}"
        )

    secret_name = r"([A-Za-z_][A-Za-z0-9_-]*)"
    key_value = re.compile(
        rf"(['\"]){secret_name}\1\s*:\s*(['\"])[^'\"]+\3",
        re.IGNORECASE,
    )
    quoted = re.compile(
        rf"\b{secret_name}\b\s*=\s*(['\"])[^'\"]+\2",
        re.IGNORECASE,
    )
    unquoted = re.compile(
        rf"\b{secret_name}\b\s*=\s*(?!['\"])[^\s;&]+",
        re.IGNORECASE,
    )
    bearer = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
    redacted = key_value.sub(replace_key_value, snippet)
    redacted = quoted.sub(replace_quoted, redacted)
    redacted = unquoted.sub(replace_unquoted, redacted)
    return bearer.sub(r"\1<redacted>", redacted)


def instance_identity(instance: dict) -> dict[str, str]:
    """Return stable instance identity fields for RQ4 outputs.

    The new corpus stores the legacy ``instance_id``/``fork``/``branch`` data in
    a single ``modification_id`` formatted ``upstream::fork_owner::fork_branch``.
    Missing parts (malformed id with fewer than three ``::`` segments) default to
    an empty string so downstream writers keep their column shape.
    """
    modification_id = instance.get("modification_id", "")
    parts = modification_id.split("::")
    fork_owner = parts[1] if len(parts) > 1 else ""
    branch = parts[2] if len(parts) > 2 else ""
    return {
        "instance_id": modification_id,
        "upstream": utils.upstream_key(instance),
        "fork_owner": fork_owner,
        "branch": branch,
    }


def scan_instance(
    instance: dict,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return security-rule matches for one branch instance."""
    return scan_instance_lines(instance, rules, roles={"added"})


def scan_instance_lines(
    instance: dict,
    rules: list[dict[str, Any]],
    roles: set[str],
    include_line_role: bool = False,
) -> list[dict[str, Any]]:
    """Return security-rule matches for selected unified-diff line roles."""
    identity = instance_identity(instance)
    matches = []
    for patch in utils.split_patch(instance.get("patch", "")):
        path = patch.get("path", "")
        file_status = patch.get("status", "")
        for line_number, role, line in diff_content_lines(
            patch.get("diff", ""),
            roles=roles,
        ):
            for rule in matching_rules_for_line(line, rules):
                role_fields = {"line_role": role} if include_line_role else {}
                matches.append(
                    {
                        **identity,
                        "path": path,
                        "file_status": file_status,
                        "patch_line": line_number,
                        **role_fields,
                        "category": rule["category"],
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "severity": rule["severity"],
                        "snippet": redact_snippet(line.strip()),
                    }
                )
    return matches


def unique_join(values: list[str]) -> str:
    """Return a semicolon-joined string preserving first occurrence order."""
    seen = set()
    unique = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return ";".join(unique)


def max_severity(matches: list[dict[str, Any]]) -> str:
    """Return the maximum match severity for one branch."""
    severity = ""
    for match in matches:
        candidate = match.get("severity", "")
        if SEVERITY_RANK[candidate] > SEVERITY_RANK[severity]:
            severity = candidate
    return severity


def rq4_security_instance_row(
    instance: dict,
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return one RQ4 static security label row from scanned matches."""
    identity = instance_identity(instance)
    return {
        **identity,
        "has_potential_security_implication": bool(matches),
        "max_severity": max_severity(matches),
        "matched_rule_ids": unique_join([match["rule_id"] for match in matches]),
        "matched_rule_names": unique_join([match["rule_name"] for match in matches]),
        "matched_categories": unique_join([match["category"] for match in matches]),
        "matched_files": unique_join([match["path"] for match in matches]),
        "match_count": len(matches),
    }


def rq4_security_instance_table(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one RQ4 static security label row per branch instance."""
    rows = []
    for instance in instances:
        matches = scan_instance(instance, rules)
        rows.append(rq4_security_instance_row(instance, matches))
    return rows


def rq4_security_match_table(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one row per security-rule match."""
    matches = []
    for instance in instances:
        matches.extend(scan_instance(instance, rules))
    return matches


def rq4_security_context_match_table(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return matches on non-added diff lines in modified security context."""
    matches = []
    for instance in instances:
        matches.extend(
            scan_instance_lines(
                instance,
                rules,
                roles={"context", "removed"},
                include_line_role=True,
            )
        )
    return matches


def rq4_security_removed_line_match_table(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return security-rule matches on removed diff lines."""
    matches = []
    for instance in instances:
        matches.extend(
            scan_instance_lines(
                instance,
                rules,
                roles={"removed"},
                include_line_role=True,
            )
        )
    return matches


def rq4_security_deleted_line_only_match_table(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return removed-line matches in changed blocks with no added-line match."""
    rows = []
    for instance in instances:
        identity = instance_identity(instance)
        for patch in utils.split_patch(instance.get("patch", "")):
            path = patch.get("path", "")
            file_status = patch.get("status", "")
            added_blocks = set()
            removed_matches = []
            for line_number, block_id, role, line in diff_changed_block_lines(
                patch.get("diff", ""),
                roles={"added", "removed"},
            ):
                matching_rules = matching_rules_for_line(line, rules)
                if not matching_rules:
                    continue
                if role == "added":
                    added_blocks.add(block_id)
                    continue
                for rule in matching_rules:
                    removed_matches.append(
                        {
                            **identity,
                            "path": path,
                            "file_status": file_status,
                            "changed_block": block_id,
                            "patch_line": line_number,
                            "line_role": role,
                            "category": rule["category"],
                            "rule_id": rule["id"],
                            "rule_name": rule["name"],
                            "severity": rule["severity"],
                            "snippet": redact_snippet(line.strip()),
                        }
                    )
            rows.extend(
                row
                for row in removed_matches
                if row["changed_block"] not in added_blocks
            )
    return rows


def rq4_security_hunk_table(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one row per diff hunk containing a security-rule match."""
    rows = []
    for instance in instances:
        identity = instance_identity(instance)
        for patch in utils.split_patch(instance.get("patch", "")):
            path = patch.get("path", "")
            file_status = patch.get("status", "")
            for hunk in diff_hunks(patch.get("diff", "")):
                line_matches = []
                for hunk_line in hunk["lines"]:
                    line = hunk_line["content"]
                    for rule in matching_rules_for_line(line, rules):
                        line_matches.append(
                            {
                                "line_role": hunk_line["role"],
                                "category": rule["category"],
                                "rule_id": rule["id"],
                                "rule_name": rule["name"],
                                "severity": rule["severity"],
                            }
                        )
                if not line_matches:
                    continue
                role_counts = Counter(match["line_role"] for match in line_matches)
                rows.append(
                    {
                        **identity,
                        "path": path,
                        "file_status": file_status,
                        "changed_block": hunk["changed_block"],
                        "hunk_status": hunk["hunk_status"],
                        "has_added_line_match": role_counts["added"] > 0,
                        "has_removed_line_match": role_counts["removed"] > 0,
                        "has_context_line_match": role_counts["context"] > 0,
                        "max_severity": max_severity(line_matches),
                        "matched_rule_ids": unique_join(
                            [match["rule_id"] for match in line_matches]
                        ),
                        "matched_rule_names": unique_join(
                            [match["rule_name"] for match in line_matches]
                        ),
                        "matched_categories": unique_join(
                            [match["category"] for match in line_matches]
                        ),
                        "added_line_match_count": role_counts["added"],
                        "removed_line_match_count": role_counts["removed"],
                        "context_line_match_count": role_counts["context"],
                        "match_count": len(line_matches),
                    }
                )
    return rows


def rq4_security_deleted_line_only_hunk_table(
    hunk_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return matched hunks with removed-line matches and no added-line match."""
    return [
        row
        for row in hunk_rows
        if row["has_removed_line_match"] and not row["has_added_line_match"]
    ]


def rq4_security_tables(
    instances: list[dict],
    rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return instance and match tables while scanning each instance once."""
    instance_rows = []
    match_rows = []
    for instance in instances:
        matches = scan_instance(instance, rules)
        instance_rows.append(rq4_security_instance_row(instance, matches))
        match_rows.extend(matches)
    return instance_rows, match_rows


def rq4_security_summary_table(
    instance_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a one-row RQ4 static security-modification summary."""
    denominator = len(instance_rows)
    security_rows = [
        row for row in instance_rows if row["has_potential_security_implication"]
    ]
    critical_rows = [row for row in instance_rows if row["max_severity"] == "CRITICAL"]
    warning_rows = [row for row in instance_rows if row["max_severity"] == "WARNING"]
    return [
        {
            "analyzed_branches": denominator,
            "branches_with_security_implication": len(security_rows),
            "security_prevalence": (
                len(security_rows) / denominator if denominator else 0.0
            ),
            "critical_branches": len(critical_rows),
            "critical_prevalence": (
                len(critical_rows) / denominator if denominator else 0.0
            ),
            "warning_branches": len(warning_rows),
            "warning_prevalence": (
                len(warning_rows) / denominator if denominator else 0.0
            ),
            "match_count": sum(row["match_count"] for row in instance_rows),
        }
    ]


def rq4_security_category_table(
    instance_rows: list[dict[str, Any]],
    match_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return branch-level prevalence and match counts by rule category."""
    denominator = len(instance_rows)
    categories = defaultdict(lambda: {"instance_ids": set(), "match_count": 0})
    for match in match_rows:
        category = match["category"]
        categories[category]["instance_ids"].add(match["instance_id"])
        categories[category]["match_count"] += 1
    rows = []
    for category, values in categories.items():
        branch_count = len(values["instance_ids"])
        rows.append(
            {
                "category": category,
                "branches": branch_count,
                "branch_prevalence": (
                    branch_count / denominator if denominator else 0.0
                ),
                "match_count": values["match_count"],
            }
        )
    return sorted(
        rows,
        key=lambda row: (-row["branches"], -row["match_count"], row["category"]),
    )


def match_instance_ids(rows: list[dict[str, Any]]) -> set[str]:
    """Return instance IDs present in a match table."""
    return {row["instance_id"] for row in rows}


def rq4_security_origin_summary_table(
    instance_rows: list[dict[str, Any]],
    added_line_matches: list[dict[str, Any]],
    context_matches: list[dict[str, Any]],
    deleted_line_only_matches: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return branch-level split between added-line and context-line matches."""
    denominator = len(instance_rows)
    deleted_line_only_matches = deleted_line_only_matches or []
    added_line_ids = match_instance_ids(added_line_matches)
    context_ids = match_instance_ids(context_matches)
    deleted_line_only_ids = match_instance_ids(deleted_line_only_matches)
    added_line_and_context = added_line_ids & context_ids
    added_line_only = added_line_ids - context_ids
    context_only = context_ids - added_line_ids
    return [
        {
            "analyzed_branches": denominator,
            "added_line_match_branches": len(added_line_ids),
            "added_line_match_prevalence": (
                len(added_line_ids) / denominator if denominator else 0.0
            ),
            "context_line_match_branches": len(context_ids),
            "context_line_match_prevalence": (
                len(context_ids) / denominator if denominator else 0.0
            ),
            "both_added_line_and_context_branches": len(added_line_and_context),
            "added_line_only_branches": len(added_line_only),
            "context_only_edit_branches": len(context_only),
            "context_only_edit_prevalence": (
                len(context_only) / denominator if denominator else 0.0
            ),
            "deleted_line_only_match_branches": len(deleted_line_only_ids),
            "deleted_line_only_match_prevalence": (
                len(deleted_line_only_ids) / denominator if denominator else 0.0
            ),
            "added_line_match_count": len(added_line_matches),
            "context_line_match_count": len(context_matches),
            "deleted_line_only_match_count": len(deleted_line_only_matches),
        }
    ]


def matches_by_category(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return match counts and instance IDs grouped by category."""
    grouped = defaultdict(lambda: {"instance_ids": set(), "match_count": 0})
    for row in rows:
        category = row["category"]
        grouped[category]["instance_ids"].add(row["instance_id"])
        grouped[category]["match_count"] += 1
    return grouped


def matches_by_pattern(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return match counts and instance IDs grouped by security rule."""
    grouped = defaultdict(lambda: {"instance_ids": set(), "match_count": 0})
    for row in rows:
        rule_id = row["rule_id"]
        values = grouped[rule_id]
        values["pattern_name"] = row["rule_name"]
        values["rule_id"] = rule_id
        values["severity"] = row["severity"]
        values["category"] = row["category"]
        values["instance_ids"].add(row["instance_id"])
        values["match_count"] += 1
    return grouped


def rq4_security_hunk_status_table(
    instance_rows: list[dict[str, Any]],
    hunk_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return branch counts grouped by matched hunk status."""
    denominator = len(instance_rows)
    grouped = defaultdict(set)
    for row in hunk_rows:
        grouped[row["hunk_status"]].add(row["instance_id"])
    rows = []
    for status, instance_ids in grouped.items():
        branches = len(instance_ids)
        rows.append(
            {
                "hunk_status": status,
                "branches": branches,
                "branch_prevalence": (
                    branches / denominator if denominator else 0.0
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-row["branches"], row["hunk_status"]),
    )


def non_removed_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return match rows outside removed file patches."""
    return [row for row in rows if row["file_status"] != "removed"]


def rq4_security_added_line_pattern_table(
    instance_rows: list[dict[str, Any]],
    added_line_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the pattern distribution for added-line security matches."""
    denominator = len(instance_rows)
    total_matches = len(added_line_matches)
    patterns = matches_by_pattern(added_line_matches)
    rows = []
    for values in patterns.values():
        instances = len(values["instance_ids"])
        match_count = values["match_count"]
        rows.append(
            {
                "pattern_name": values["pattern_name"],
                "rule_id": values["rule_id"],
                "severity": values["severity"],
                "category": values["category"],
                "instances": instances,
                "branch_prevalence": (
                    instances / denominator if denominator else 0.0
                ),
                "match_count": match_count,
                "match_share": (
                    match_count / total_matches if total_matches else 0.0
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-row["instances"], -row["match_count"], row["pattern_name"]),
    )


def rq4_security_line_edit_split_table(
    instance_rows: list[dict[str, Any]],
    added_line_matches: list[dict[str, Any]],
    removed_line_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return added-line matches and remaining deleted-line matches."""
    denominator = len(instance_rows)
    added_line_ids = match_instance_ids(non_removed_matches(added_line_matches))
    removed_line_ids = match_instance_ids(non_removed_matches(removed_line_matches))
    deleted_line_ids = removed_line_ids - added_line_ids
    total_ids = added_line_ids | deleted_line_ids
    total = len(total_ids)
    rows = [
        ("added_line", len(added_line_ids)),
        ("remaining_deleted_line", len(deleted_line_ids)),
    ]
    return [
        {
            "edit_type": edit_type,
            "instances": instances,
            "branch_prevalence": instances / denominator if denominator else 0.0,
            "edit_share": instances / total if total else 0.0,
        }
        for edit_type, instances in rows
    ]


def rq4_security_origin_category_table(
    instance_rows: list[dict[str, Any]],
    added_line_matches: list[dict[str, Any]],
    context_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return added-line and context-line counts by rule category."""
    denominator = len(instance_rows)
    added_line = matches_by_category(added_line_matches)
    context = matches_by_category(context_matches)
    categories = set(added_line) | set(context)
    rows = []
    for category in categories:
        added_line_ids = added_line[category]["instance_ids"]
        context_ids = context[category]["instance_ids"]
        context_only_ids = context_ids - added_line_ids
        rows.append(
            {
                "category": category,
                "added_line_match_branches": len(added_line_ids),
                "added_line_match_prevalence": (
                    len(added_line_ids) / denominator if denominator else 0.0
                ),
                "context_line_match_branches": len(context_ids),
                "context_line_match_prevalence": (
                    len(context_ids) / denominator if denominator else 0.0
                ),
                "context_only_edit_branches": len(context_only_ids),
                "context_only_edit_prevalence": (
                    len(context_only_ids) / denominator if denominator else 0.0
                ),
                "added_line_match_count": added_line[category]["match_count"],
                "context_line_match_count": context[category]["match_count"],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -(
                row["added_line_match_branches"]
                + row["context_line_match_branches"]
            ),
            -row["context_line_match_branches"],
            -row["added_line_match_branches"],
            row["category"],
        ),
    )


def rq4_security_origin_pattern_table(
    instance_rows: list[dict[str, Any]],
    added_line_matches: list[dict[str, Any]],
    context_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return added-line and context-line counts by security rule name."""
    denominator = len(instance_rows)
    added_line = matches_by_pattern(added_line_matches)
    context = matches_by_pattern(context_matches)
    rule_ids = set(added_line) | set(context)
    rows = []
    for rule_id in rule_ids:
        added_line_ids = added_line[rule_id]["instance_ids"]
        context_ids = context[rule_id]["instance_ids"]
        context_only_ids = context_ids - added_line_ids
        values = added_line.get(rule_id) or context[rule_id]
        rows.append(
            {
                "pattern_name": values["pattern_name"],
                "rule_id": rule_id,
                "severity": values["severity"],
                "added_line_match_branches": len(added_line_ids),
                "added_line_match_prevalence": (
                    len(added_line_ids) / denominator if denominator else 0.0
                ),
                "context_line_match_branches": len(context_ids),
                "context_line_match_prevalence": (
                    len(context_ids) / denominator if denominator else 0.0
                ),
                "context_only_edit_branches": len(context_only_ids),
                "context_only_edit_prevalence": (
                    len(context_only_ids) / denominator if denominator else 0.0
                ),
                "added_line_match_count": added_line[rule_id]["match_count"],
                "context_line_match_count": context[rule_id]["match_count"],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -(
                row["added_line_match_branches"]
                + row["context_line_match_branches"]
            ),
            -row["context_line_match_branches"],
            -row["added_line_match_branches"],
            row["pattern_name"],
        ),
    )


def rq4_security_status_table(
    instance_rows: list[dict[str, Any]],
    added_line_matches: list[dict[str, Any]],
    removed_line_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return branch counts by non-removed file patch status."""
    denominator = len(instance_rows)
    grouped = defaultdict(set)
    for row in added_line_matches + removed_line_matches:
        file_status = row["file_status"]
        if file_status == "removed":
            continue
        grouped[file_status].add(row["instance_id"])
    rows = []
    for file_status, instance_ids in grouped.items():
        instances = len(instance_ids)
        rows.append(
            {
                "file_status": file_status,
                "instances": instances,
                "branch_prevalence": instances / denominator if denominator else 0.0,
            }
        )
    return sorted(
        rows,
        key=lambda row: (-row["instances"], row["file_status"]),
    )


def matches_by_file_status(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return match counts and instance IDs grouped by file patch status."""
    grouped = defaultdict(lambda: {"instance_ids": set(), "match_count": 0})
    for row in rows:
        file_status = row["file_status"]
        grouped[file_status]["instance_ids"].add(row["instance_id"])
        grouped[file_status]["match_count"] += 1
    return grouped


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> Path:
    """Write rows to CSV with stable column order.

    Float-valued cells (prevalences, shares, lifts) are rounded to 4 decimals
    for consistency with the other RQ tables; ints and strings are untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.4f}" if isinstance(v, float) else v)
                for k, v in row.items()
            })
    return path


def write_rq4_outputs(
    instances: list[dict],
    rules_path: str | Path = DEFAULT_RULES,
    out_dir: str | Path = DEFAULT_OUT_DIR,
) -> dict[
    Literal[
        "instances_csv",
        "matches_csv",
        "summary_csv",
        "categories_csv",
        "context_matches_csv",
        "deleted_line_only_matches_csv",
        "hunks_csv",
        "deleted_line_only_hunks_csv",
        "hunk_status_csv",
        "added_line_patterns_csv",
        "line_edit_split_csv",
        "origin_summary_csv",
        "origin_categories_csv",
        "origin_patterns_csv",
        "status_csv",
    ],
    Path,
]:
    """Write RQ4 security instance, match, and summary CSVs."""
    target = Path(out_dir)
    rules = load_security_rules(rules_path)
    instance_rows, match_rows = rq4_security_tables(instances, rules)
    context_rows = rq4_security_context_match_table(instances, rules)
    removed_line_rows = rq4_security_removed_line_match_table(instances, rules)
    deleted_line_only_rows = rq4_security_deleted_line_only_match_table(
        instances,
        rules,
    )
    hunk_rows = rq4_security_hunk_table(instances, rules)
    deleted_line_only_hunk_rows = rq4_security_deleted_line_only_hunk_table(
        hunk_rows,
    )
    summary_rows = rq4_security_summary_table(instance_rows)
    category_rows = rq4_security_category_table(instance_rows, match_rows)
    hunk_status_rows = rq4_security_hunk_status_table(instance_rows, hunk_rows)
    added_line_pattern_rows = rq4_security_added_line_pattern_table(
        instance_rows,
        match_rows,
    )
    line_edit_split_rows = rq4_security_line_edit_split_table(
        instance_rows,
        match_rows,
        removed_line_rows,
    )
    origin_summary_rows = rq4_security_origin_summary_table(
        instance_rows,
        match_rows,
        context_rows,
        deleted_line_only_rows,
    )
    origin_category_rows = rq4_security_origin_category_table(
        instance_rows,
        match_rows,
        context_rows,
    )
    origin_pattern_rows = rq4_security_origin_pattern_table(
        instance_rows,
        match_rows,
        context_rows,
    )
    status_rows = rq4_security_status_table(
        instance_rows,
        match_rows,
        removed_line_rows,
    )
    return {
        "instances_csv": write_csv(
            target / "rq4-security-instances.csv",
            instance_rows,
            INSTANCE_FIELDNAMES,
        ),
        "matches_csv": write_csv(
            target / "rq4-security-matches.csv",
            match_rows,
            MATCH_FIELDNAMES,
        ),
        "summary_csv": write_csv(
            target / "rq4-security-summary.csv",
            summary_rows,
            SUMMARY_FIELDNAMES,
        ),
        "categories_csv": write_csv(
            target / "rq4-security-categories.csv",
            category_rows,
            CATEGORY_FIELDNAMES,
        ),
        "context_matches_csv": write_csv(
            target / "rq4-security-context-matches.csv",
            context_rows,
            CONTEXT_MATCH_FIELDNAMES,
        ),
        "deleted_line_only_matches_csv": write_csv(
            target / "rq4-security-deleted-line-only-matches.csv",
            deleted_line_only_rows,
            DELETED_LINE_ONLY_MATCH_FIELDNAMES,
        ),
        "hunks_csv": write_csv(
            target / "rq4-security-hunks.csv",
            hunk_rows,
            HUNK_FIELDNAMES,
        ),
        "deleted_line_only_hunks_csv": write_csv(
            target / "rq4-security-deleted-line-only-hunks.csv",
            deleted_line_only_hunk_rows,
            HUNK_FIELDNAMES,
        ),
        "hunk_status_csv": write_csv(
            target / "rq4-security-hunk-status.csv",
            hunk_status_rows,
            HUNK_STATUS_FIELDNAMES,
        ),
        "added_line_patterns_csv": write_csv(
            target / "rq4-security-added-line-patterns.csv",
            added_line_pattern_rows,
            ADDED_LINE_PATTERN_FIELDNAMES,
        ),
        "line_edit_split_csv": write_csv(
            target / "rq4-security-line-edit-split.csv",
            line_edit_split_rows,
            LINE_EDIT_SPLIT_FIELDNAMES,
        ),
        "origin_summary_csv": write_csv(
            target / "rq4-security-origin-summary.csv",
            origin_summary_rows,
            ORIGIN_SUMMARY_FIELDNAMES,
        ),
        "origin_categories_csv": write_csv(
            target / "rq4-security-origin-categories.csv",
            origin_category_rows,
            ORIGIN_CATEGORY_FIELDNAMES,
        ),
        "origin_patterns_csv": write_csv(
            target / "rq4-security-origin-patterns.csv",
            origin_pattern_rows,
            ORIGIN_PATTERN_FIELDNAMES,
        ),
        "status_csv": write_csv(
            target / "rq4-security-status.csv",
            status_rows,
            STATUS_FIELDNAMES,
        ),
    }


def main() -> None:
    """CLI entry point for RQ4 static security analysis."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, default=DEFAULT_INSTANCES)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--num_samples", type=int, default=None,
                        help="limit to the first N instances for a dry run")
    args = parser.parse_args()

    instances = utils.load_instances(args.instances)
    if args.num_samples is not None:
        instances = instances[: args.num_samples]
    outputs = write_rq4_outputs(instances, rules_path=args.rules, out_dir=args.out_dir)

    summary = rq4_security_summary_table(
        rq4_security_instance_table(instances, load_security_rules(args.rules))
    )[0]
    logger.info(
        "instances=%d security_branches=%d security_prevalence=%.1f%%",
        len(instances),
        summary["branches_with_security_implication"],
        100 * summary["security_prevalence"],
    )
    logger.info("wrote %d CSVs to %s", len(outputs), args.out_dir)


if __name__ == "__main__":
    main()
