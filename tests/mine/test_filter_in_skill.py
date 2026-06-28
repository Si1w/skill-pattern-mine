from mine.s05_filter_in_skill import filter_files

# Existing skill directories upstream (SKILL.md parents).
DIRS = {"skills/foo", "skills/bar"}


def _names(files):
    return [f["filename"] for f in files]


def test_keeps_in_skill_modification():
    files = [{"filename": "skills/foo/SKILL.md", "status": "modified"},
             {"filename": "skills/foo/scripts/run.py", "status": "modified"}]
    assert _names(filter_files(files, DIRS)) == [
        "skills/foo/SKILL.md", "skills/foo/scripts/run.py"]


def test_drops_added_skill():
    files = [{"filename": "skills/new/SKILL.md", "status": "added"},
             {"filename": "skills/new/helper.py", "status": "added"}]
    assert filter_files(files, DIRS) == []


def test_drops_removed_skill():
    files = [{"filename": "skills/bar/SKILL.md", "status": "removed"}]
    assert filter_files(files, DIRS) == []


def test_drops_non_skill_files():
    files = [{"filename": "README.md", "status": "modified"},
             {"filename": ".github/workflows/ci.yml", "status": "modified"}]
    assert filter_files(files, DIRS) == []


def test_keeps_edit_drops_added_skill_in_same_diff():
    files = [{"filename": "skills/foo/SKILL.md", "status": "modified"},
             {"filename": "skills/new/SKILL.md", "status": "added"}]
    assert _names(filter_files(files, DIRS)) == ["skills/foo/SKILL.md"]


def test_nested_added_sub_skill_is_dropped():
    # A sub-skill created under an existing skill dir is add-skill, not an edit.
    files = [{"filename": "skills/foo/child/SKILL.md", "status": "added"},
             {"filename": "skills/foo/child/helper.py", "status": "added"}]
    assert filter_files(files, DIRS) == []
