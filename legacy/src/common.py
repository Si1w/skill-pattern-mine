"""Shared commit-message helpers used across mine / label / eval stages.

Filters mechanical / aggregated / boilerplate commits by subject pattern and
trims auto-generated footer lines. These commits carry no fork-author intent
for *skill modification* mining:

- ``merge_pr`` / ``merge_branch`` / ``merge_other``: PR / branch / upstream
  merges; the body is either empty or an aggregation of other commits.
- ``squashed`` / ``squashed_subtree``: rebase-squash and subtree merges.
- ``release_note``: changelog aggregations, not specific modifications.
- ``update_readme``: bare ``Update README.md`` (GitHub web-edit default).
- ``revert``: undoes prior work, not a positive intent.
- ``initial_commit`` / ``create_using`` / ``empty``: trivial / template.

Apply via :func:`filter_commits` (on ``[{sha, message}, ...]``) or
:func:`is_noise` for a single message.
"""

import re

FOOTER_LINE_RE = re.compile(
    r"^(?:Co-Authored-By|Signed-off-by|Reviewed-by|Cc|Generated with|🤖 Generated|"
    r"Reported-by|Closes|Fixes|Refs|Resolves|See|Tested-by|Acked-by):.*$",
    re.IGNORECASE | re.MULTILINE,
)
BLANK_LINES_RE = re.compile(r"\n{3,}")

NOISE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("squashed",         re.compile(r"^Squashed commit of the following:")),
    ("squashed_subtree", re.compile(r"^Squashed '.*' (changes|content) from")),
    ("merge_pr",         re.compile(r"^Merge pull request #\d+")),
    ("merge_branch",     re.compile(r"^Merge (branch|remote-tracking|tag|commit|upstream|origin) ", re.I)),
    ("merge_other",      re.compile(r"^Merge\b(?! pull request| branch| remote| tag| commit| upstream| origin)", re.I)),
    ("revert",           re.compile(r"^Revert ['\"]")),
    ("release_note",     re.compile(r"^(Release\s+v?\d+\.\d+|v?\d+\.\d+\.\d+(\s|\b)|Bump version)", re.I)),
    ("initial_commit",   re.compile(r"^Initial commit$", re.I)),
    ("update_readme",    re.compile(r"^Update README(\.md)?$", re.I)),
    ("create_using",     re.compile(r"^Created? (using|with) ", re.I)),
]


def classify(message: str) -> str | None:
    """Return the noise category name, or ``None`` if the message is normal."""
    if not message or not message.strip():
        return "empty"
    subject = message.strip().splitlines()[0]
    for name, rx in NOISE_PATTERNS:
        if rx.match(subject):
            return name
    return None


def is_noise(message: str) -> bool:
    """True iff ``message`` matches any noise pattern (or is empty)."""
    return classify(message) is not None


def filter_messages(messages: list[str]) -> list[str]:
    """Drop noise messages from a flat list."""
    return [m for m in messages if not is_noise(m)]


def filter_commits(commits: list[dict]) -> list[dict]:
    """Drop noise entries from a ``[{sha, message}, ...]`` list."""
    return [c for c in commits if not is_noise(c.get("message", ""))]


def trim_message(message: str) -> str:
    """Remove auto-generated footer lines (Co-Authored-By, Signed-off-by, etc.).

    Operates per-line: each matching line is replaced with empty, then runs of
    3+ consecutive newlines are collapsed back to 2. The rest is left intact.
    """
    cleaned = FOOTER_LINE_RE.sub("", message)
    cleaned = BLANK_LINES_RE.sub("\n\n", cleaned).strip()
    return cleaned


def trim_messages(messages: list[str]) -> list[str]:
    """Apply :func:`trim_message` to every message."""
    return [trim_message(m) for m in messages]
