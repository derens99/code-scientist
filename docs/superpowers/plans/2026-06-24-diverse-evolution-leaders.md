# Diverse Evolution Leaders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make evolution parent selection use the proximity graph so the supervisor spends child-generation budget across distinct accepted hypotheses instead of evolving near-duplicate leaders.

**Architecture:** Add a small supervisor helper that sorts active hypotheses by Elo, selects the strongest leader first, then prefers additional leaders that are not high-similarity or deduplication-controlled neighbors of already selected leaders. Wire the helper into `run_research_cycle` where the evolution task payload and trace input refs are built.

**Tech Stack:** Python dataclasses, existing `Hypothesis` and `ProximityEdge` models, pytest, existing supervisor task queue.

---

### Task 1: Failing Unit Test

**Files:**
- Modify: `tests/test_supervisor.py`

- [x] **Step 1: Add the failing test near the proximity scheduling tests**

```python
def test_select_diverse_evolution_leaders_prefers_cluster_coverage():
    leader = _hypothesis("hyp-leader", elo=1300.0).with_status("accepted")
    near_duplicate = _hypothesis("hyp-near", elo=1290.0).with_status("accepted")
    diverse = _hypothesis("hyp-diverse", elo=1240.0).with_status("accepted")
    edges = [
        ProximityEdge(
            source=leader.id,
            target=near_duplicate.id,
            similarity=0.95,
            method="embedding_proximity",
            reason="Same repair-loop mechanism.",
            deduplication_action="merge_or_contrast_before_ranking",
            diversity_action="avoid_redundant_parallel_exploration",
        ),
        ProximityEdge(
            source=leader.id,
            target=diverse.id,
            similarity=0.15,
            method="embedding_proximity",
            reason="Different UI inspection mechanism.",
            diversity_action="preserve_as_diversity_candidate",
        ),
    ]

    selected = supervisor_module._select_diverse_evolution_leaders(
        [leader, near_duplicate, diverse],
        edges,
        limit=2,
    )

    assert [item.id for item in selected] == ["hyp-leader", "hyp-diverse"]
```

- [x] **Step 2: Run the test and confirm RED**

Run: `uv run pytest tests/test_supervisor.py::test_select_diverse_evolution_leaders_prefers_cluster_coverage -q`

Expected: FAIL because `_select_diverse_evolution_leaders` does not exist.

### Task 2: Minimal Helper and Wiring

**Files:**
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Add a helper that prefers non-redundant accepted leaders**

```python
def _select_diverse_evolution_leaders(
    hypotheses: list[Hypothesis],
    proximity_edges: list[ProximityEdge],
    limit: int = 2,
) -> list[Hypothesis]:
    if limit <= 0:
        return []
    active = [
        item
        for item in sorted(hypotheses, key=lambda hyp: hyp.elo, reverse=True)
        if item.status != "merged_duplicate"
    ]
    edge_by_pair = {_pair_key(edge.source, edge.target): edge for edge in proximity_edges}
    selected: list[Hypothesis] = []
    for candidate in active:
        if len(selected) >= limit:
            break
        if not selected or not any(
            _is_redundant_evolution_pair(candidate, chosen, edge_by_pair)
            for chosen in selected
        ):
            selected.append(candidate)
    selected_ids = {item.id for item in selected}
    for candidate in active:
        if len(selected) >= limit:
            break
        if candidate.id not in selected_ids:
            selected.append(candidate)
            selected_ids.add(candidate.id)
    return selected
```

- [x] **Step 2: Add the pair-redundancy predicate**

```python
def _is_redundant_evolution_pair(
    candidate: Hypothesis,
    selected: Hypothesis,
    edge_by_pair: dict[str, ProximityEdge],
) -> bool:
    edge = edge_by_pair.get(_pair_key(candidate.id, selected.id))
    if edge is None:
        return False
    if edge.deduplication_action == "merge_or_contrast_before_ranking":
        return True
    if edge.diversity_action == "preserve_as_diversity_candidate":
        return False
    return edge.similarity >= 0.8
```

- [x] **Step 3: Replace the current Elo-only leader selection**

Change:

```python
leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:2]
```

To:

```python
leaders = _select_diverse_evolution_leaders(hypotheses, proximity_edges, limit=2)
```

- [x] **Step 4: Run the focused test and confirm GREEN**

Run: `uv run pytest tests/test_supervisor.py::test_select_diverse_evolution_leaders_prefers_cluster_coverage -q`

Expected: PASS.

### Task 3: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-diverse-evolution-leaders.md`

- [x] **Step 1: Update the roadmap**

Record slice 119 and narrow the proximity remaining gap from broad diversity-aware resource allocation to broader resource allocation beyond evolution leader selection.

- [x] **Step 2: Run verification**

Run:

```bash
uv run pytest tests/test_supervisor.py::test_select_diverse_evolution_leaders_prefers_cluster_coverage tests/test_supervisor.py::test_schedule_pairs_skips_merged_duplicate_hypotheses -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
uv run python -m py_compile src/code_scientist/supervisor.py
git diff --check
```

Expected: all commands exit 0.
