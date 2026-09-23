"""Build a portable, answer-free annotation package for the rebuttal branch."""

import hashlib
import json
from pathlib import Path
import re
import sys

LEGACY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LEGACY))
from eval.rebuttal.audit_materials import write_form

SOURCE = LEGACY / "data/rebuttal/human-293-20260923/human"
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
    manifest = {"run_id": "human-293-20260923", "population": 1220, "blind_sample": 293,
                "security_instances": 209, "security_lines": 1521,
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
                                         "tasks": len(payload["tasks"])}
    (TARGET / "package.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
