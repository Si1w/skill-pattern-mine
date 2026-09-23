"""Build a portable, answer-free annotation package for the rebuttal branch."""

import hashlib
import json
from pathlib import Path
import re
import sys

LEGACY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LEGACY))
from eval.rebuttal.audit_materials import write_form

SOURCE = LEGACY / "data/rebuttal/human-unseen-v2-20260923/human"
TARGET = LEGACY / "annotation"
SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.S),
]


def sanitize(value):
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            value = pattern.sub("<REDACTED_CREDENTIAL>", value)
        return value
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def main():
    TARGET.mkdir(exist_ok=True)
    selection = json.loads((SOURCE / "coordinator_blind_manifest.json").read_text())
    security_scope = json.loads((SOURCE / "security_scope.json").read_text())
    manifest = {"run_id": selection["run_id"], "population": selection["population"],
                "frame": selection["frame"], "blind_sample": selection["sample_size"],
                "audit_overlap": selection["audit_overlap"], "bootstrap_overlap": selection["bootstrap_overlap"],
                "supersedes_blind_run": "human-293-20260923",
                "security_instances": security_scope["eligible_positive_instances"],
                "security_lines": security_scope["eligible_matched_lines"],
                "security_scope": security_scope,
                "answer_fields_included": False,
                "redaction": "Credential-shaped strings are replaced; task IDs and sample membership are unchanged.",
                "files": {}}
    for mode in ["blind", "security"]:
        source = SOURCE / (mode + ".html")
        text = source.read_text()
        payload = json.loads(re.search(r'<script id="payload" type="application/json">(.*?)</script>', text, re.S).group(1))
        for task in payload["tasks"]:
            if any(key in task for key in ["labels", "predicted_labels", "rationale", "label_assignments"]):
                raise ValueError("Model answer field present in annotation task")
        destination = TARGET / source.name
        write_form(destination, sanitize(payload))
        manifest["files"][source.name] = {"sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                                         "run_id": payload["run_id"],
                                         "tasks": len(payload["tasks"])}
    (TARGET / "package.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
