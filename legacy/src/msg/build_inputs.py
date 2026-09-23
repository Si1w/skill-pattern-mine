"""Split the message-only instances into isolated, gt-free labeler inputs.

``data/analysis/msg_instances.jsonl`` carries ``msg`` and ``gt_labels`` on the
same line, so a labeler that reads it sees the patch-derived ground truth in its
context. The message-only experiment must judge how much signal the commit
messages carry on their own, so the labeler has to be *mechanically* blind to
gt — not merely instructed to ignore it.

This builder enforces that isolation by writing one gt-free input per instance,
mirroring the ``label`` pipeline (``data/label/inputs/``):

- ``data/msg/inputs/{stem}.json`` — one file per instance, ``modification_id`` +
  ``msg`` only. This is the sole input a labeler reads; it contains no gt.

The ground truth is *not* copied out. The scorer reads ``gt_labels`` directly
from ``msg_instances.jsonl`` (which the labeler never opens), so there is no
separate gt file to keep in sync.

Filenames use the same ``instance_stem`` slug as the label pipeline, so an
instance keeps one stable filename across label, audit, and msg.

Usage:
    uv run python -m msg.build_inputs
"""

import argparse
import json
import logging
from pathlib import Path

from label.instance import instance_stem

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_SRC = Path("data/analysis/msg_instances.jsonl")
DEFAULT_INPUTS_DIR = Path("data/msg/inputs")


def stem_for(modification_id: str) -> str:
    """Derive the shared filename stem from an ``upstream::owner::branch`` id."""
    upstream, fork_owner, fork_branch = modification_id.split("::")
    return instance_stem(upstream, fork_owner, fork_branch)


def build(src: Path, inputs_dir: Path) -> int:
    """Write one gt-free input per instance. Returns the number written."""
    inputs_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            mid = rec["modification_id"]

            # Labeler input: messages only, never gt_labels.
            inp = {"modification_id": mid, "msg": rec.get("msg", [])}
            (inputs_dir / f"{stem_for(mid)}.json").write_text(
                json.dumps(inp, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            n += 1
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--inputs_dir", default=str(DEFAULT_INPUTS_DIR))
    args = parser.parse_args()

    n = build(Path(args.src), Path(args.inputs_dir))
    logger.info("wrote %d inputs to %s", n, args.inputs_dir)


if __name__ == "__main__":
    main()
