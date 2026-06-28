import json
import uuid

from analysis.sanitize_release import (
    pseudonymize_modification_id,
    sanitize_diff,
    sanitize_fork,
    sanitize_instance,
    write_sanitized_jsonl,
)


def instance():
    return {
        "modification_id": "ComposioHQ/awesome-claude-skills::alice::master",
        "upstream": "ComposioHQ/awesome-claude-skills",
        "commit_messages": [
            "Fix typo\n\nUse /home/alice/.config with api_key=sk-abcdefghijklmnopqrstuvwxyz"
        ],
        "patch": "+Read /Users/alice/.env and use token=ghp_abcdefghijklmnopqrstuvwxyz",
        "labels": ["modify-skill-metadata"],
    }


def diff():
    return {
        "upstream": "ComposioHQ/awesome-claude-skills",
        "fork_owner": "alice",
        "fork_branch": "master",
        "merge_base_sha": "abc123def456abc123def456abc123def456abc1",
        "head_sha": "def456abc123def456abc123def456abc123def4",
        "commits": [{"sha": "aaa111", "message": "init"}],
        "files": [{"filename": "SKILL.md", "patch": "+hello"}],
    }


def fork():
    return {
        "upstream": "ComposioHQ/awesome-claude-skills",
        "owner": "alice",
        "full_name": "alice/awesome-claude-skills",
        "clone_url": "https://github.com/alice/awesome-claude-skills.git",
        "name": "awesome-claude-skills",
        "stargazers_count": 0,
    }


# --- pseudonymize_modification_id ---

def test_pseudonymize_modification_id_returns_valid_uuid():
    result = pseudonymize_modification_id("upstream/repo::alice::main")
    parsed = uuid.UUID(result)
    assert parsed.version == 5


def test_pseudonymize_modification_id_is_stable():
    a = pseudonymize_modification_id("upstream/repo::alice::main")
    b = pseudonymize_modification_id("upstream/repo::alice::main")
    assert a == b


def test_pseudonymize_modification_id_differs_for_different_owners():
    a = pseudonymize_modification_id("upstream/repo::alice::main")
    b = pseudonymize_modification_id("upstream/repo::bob::main")
    assert a != b


def test_pseudonymize_modification_id_unchanged_when_malformed():
    raw = "no-double-colons-here"
    assert pseudonymize_modification_id(raw) == raw


# --- sanitize_instance ---

def test_sanitize_instance_modification_id_is_uuid():
    row = sanitize_instance(instance())
    parsed = uuid.UUID(row["modification_id"])
    assert parsed.version == 5


def test_sanitize_instance_redacts_secrets_and_local_paths():
    row = sanitize_instance(instance())
    text = json.dumps(row)

    assert "ghp_abcdefghijklmnopqrstuvwxyz" not in text
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in text
    assert "/Users/alice" not in text
    assert "/home/alice" not in text
    assert "<REDACTED>" in text
    assert "<LOCAL_USER_PATH>" in text


def test_sanitize_instance_preserves_labels_and_upstream():
    row = sanitize_instance(instance())
    assert row["labels"] == ["modify-skill-metadata"]
    assert row["upstream"] == "ComposioHQ/awesome-claude-skills"


# --- sanitize_diff ---

def test_sanitize_diff_pseudonymizes_fork_owner():
    row = sanitize_diff(diff())
    assert row["fork_owner"].startswith("fork-owner-")
    assert row["fork_owner"] != "alice"


def test_sanitize_diff_pseudonymizes_shas():
    row = sanitize_diff(diff())
    assert row["merge_base_sha"].startswith("sha-")
    assert row["head_sha"].startswith("sha-")
    assert row["commits"][0]["sha"].startswith("sha-")


def test_sanitize_diff_preserves_upstream_and_branch():
    row = sanitize_diff(diff())
    assert row["upstream"] == "ComposioHQ/awesome-claude-skills"
    assert row["fork_branch"] == "master"


# --- sanitize_fork ---

def test_sanitize_fork_pseudonymizes_owner():
    row = sanitize_fork(fork())
    assert row["owner"].startswith("fork-owner-")
    assert "alice" not in row["owner"]


def test_sanitize_fork_replaces_owner_in_full_name_and_clone_url():
    row = sanitize_fork(fork())
    assert "alice" not in row["full_name"]
    assert "alice" not in row["clone_url"]
    assert row["owner"] in row["full_name"]
    assert row["owner"] in row["clone_url"]


def test_sanitize_fork_preserves_non_sensitive_fields():
    row = sanitize_fork(fork())
    assert row["upstream"] == "ComposioHQ/awesome-claude-skills"
    assert row["name"] == "awesome-claude-skills"
    assert row["stargazers_count"] == 0


# --- write_sanitized_jsonl ---

def test_write_sanitized_jsonl_instance(tmp_path):
    input_path = tmp_path / "instances.jsonl"
    out_path = tmp_path / "instances.public.jsonl"
    input_path.write_text(json.dumps(instance()) + "\n")

    count = write_sanitized_jsonl(input_path, out_path, kind="instance")

    assert count == 1
    row = json.loads(out_path.read_text())
    uuid.UUID(row["modification_id"])


def test_write_sanitized_jsonl_diff(tmp_path):
    input_path = tmp_path / "diffs.jsonl"
    out_path = tmp_path / "diffs.public.jsonl"
    input_path.write_text(json.dumps(diff()) + "\n")

    count = write_sanitized_jsonl(input_path, out_path, kind="diff")

    assert count == 1
    row = json.loads(out_path.read_text())
    assert row["fork_owner"].startswith("fork-owner-")


def test_write_sanitized_jsonl_fork(tmp_path):
    input_path = tmp_path / "forks.jsonl"
    out_path = tmp_path / "forks.public.jsonl"
    input_path.write_text(json.dumps(fork()) + "\n")

    count = write_sanitized_jsonl(input_path, out_path, kind="fork")

    assert count == 1
    row = json.loads(out_path.read_text())
    assert row["owner"].startswith("fork-owner-")
