from analysis.build_instances import dedup_branch_subsets


def _rec(mod_id, shas):
    """Minimal record carrying a modification_id and a commit SHA list."""
    return {
        "modification_id": mod_id,
        "commits": [{"sha": s, "message": ""} for s in shas],
    }


def _ids(recs):
    return {r["modification_id"] for r in recs}


def test_keeps_single_branch_fork():
    recs = [_rec("up::alice::main", ["a", "b"])]
    assert _ids(dedup_branch_subsets(recs)) == {"up::alice::main"}


def test_drops_exact_duplicate_branch():
    # Same owner, two branches with identical commit sets -> keep one.
    recs = [
        _rec("up::alice::main", ["a", "b"]),
        _rec("up::alice::dev", ["a", "b"]),
    ]
    assert len(dedup_branch_subsets(recs)) == 1


def test_drops_subset_keeps_superset():
    # dev's commits are a subset of main's -> drop dev, keep main.
    recs = [
        _rec("up::alice::main", ["a", "b", "c"]),
        _rec("up::alice::dev", ["a", "b"]),
    ]
    assert _ids(dedup_branch_subsets(recs)) == {"up::alice::main"}


def test_keeps_disjoint_branches():
    # Different commit lines, neither contains the other -> keep both.
    recs = [
        _rec("up::alice::main", ["a", "b"]),
        _rec("up::alice::feat", ["c", "d"]),
    ]
    assert _ids(dedup_branch_subsets(recs)) == {"up::alice::main", "up::alice::feat"}


def test_different_owners_never_collapse():
    # Identical SHAs but different owners stay separate (cross-owner is shared
    # upstream history's concern, not per-fork branch dedup).
    recs = [
        _rec("up::alice::main", ["a", "b"]),
        _rec("up::bob::main", ["a", "b"]),
    ]
    assert len(dedup_branch_subsets(recs)) == 2


def test_different_upstream_same_owner_never_collapse():
    recs = [
        _rec("up1::alice::main", ["a", "b"]),
        _rec("up2::alice::main", ["a", "b"]),
    ]
    assert len(dedup_branch_subsets(recs)) == 2


def test_three_branches_chain():
    # c2 subset of c1, c3 subset of c1 -> only the superset c1 survives.
    recs = [
        _rec("up::alice::c1", ["a", "b", "c"]),
        _rec("up::alice::c2", ["a", "b"]),
        _rec("up::alice::c3", ["a"]),
    ]
    assert _ids(dedup_branch_subsets(recs)) == {"up::alice::c1"}
