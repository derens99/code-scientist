# Paper Alignment Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Code Scientist control loop behave the way the co-scientist paper describes it — fix the seven verified defects and de-stub two named mechanisms (spec: `docs/superpowers/specs/2026-07-04-paper-alignment-wave1-design.md`).

**Architecture:** All changes modify existing modules (`supervisor.py`, `agents.py`, `models.py`, `safety.py`, `tools.py`, `reporting.py`) in place; no new subsystems. Every task is TDD against the existing deterministic test patterns in `tests/` (invoke `run_research_cycle(...)` with small budgets, assert on returned `RunState`). Old `state.json` files must keep loading (tolerant `from_dict` defaults).

**Tech Stack:** Python 3.12 + dataclasses, pytest via `uv run pytest`, stdlib only (no new deps). Web workbench untouched except where noted.

**Conventions for every task:** run tests with `uv run pytest tests/<file>::<test> -q`; commit on the feature branch `feature/paper-alignment-wave1`; never use `pip`/bare `python` — always `uv run`. When a step says "locate", use the given anchor (function name + approximate line) — line numbers may drift a few lines.

---

### Task 1: Web-search default endpoint/parser fix (spec item 7)

The HTML fallback parser (`tools.py` `_HTMLWebSearchResultParser`, ~line 930) targets DuckDuckGo markup (`result__a`, `result__snippet`, `/l/?uddg=`), but the default `base_url` is `https://www.bing.com/search` with a hardcoded `format=rss` query param (`tools.py:184,206`). Fix: default to the DuckDuckGo HTML endpoint and only send `format=rss` when explicitly configured.

**Files:**
- Modify: `src/code_scientist/tools.py` (`WebSearchTool.__init__` ~179, `search` ~206)
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test.** Follow the existing `test_web_search_tool_*` monkeypatch pattern in `tests/test_tools.py` (they stub `urlopen`); add:

```python
def test_web_search_tool_default_endpoint_matches_html_parser(monkeypatch):
    captured_urls: list[str] = []

    duckduckgo_html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fswe-bench">SWE-bench overview</a>
        <div class="result__snippet">Benchmark for resolving real GitHub issues.</div>
      </div>
      <div class="result">
        <a class="result__a" href="https://example.com/agents">Coding agents survey</a>
        <div class="result__snippet">A survey of LLM coding agents.</div>
      </div>
    </body></html>
    """

    class FakeResponse:
        headers = {"content-type": "text/html; charset=utf-8"}
        def read(self, _max_bytes): return duckduckgo_html.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *args): return False
        @property
        def headers(self):  # noqa: F811 - simple stub
            class H(dict):
                def get(self, key, default=""): return "text/html; charset=utf-8"
            return H()

    def fake_urlopen(request, timeout=0):
        captured_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr("code_scientist.tools.urlopen", fake_urlopen)

    result = WebSearchTool().search("swe-bench coding agents", limit=5)

    assert "duckduckgo.com" in captured_urls[0]
    assert "format=rss" not in captured_urls[0]
    assert len(result.evidence) == 2
    assert result.evidence[0].metadata["url"] == "https://example.com/swe-bench"
```

(Adapt the stub-response shape to whatever helper the neighboring web-search tests already use — reuse their fake-response class if one exists instead of redefining.)

- [ ] **Step 2: Run it to verify it fails.** `uv run pytest tests/test_tools.py::test_web_search_tool_default_endpoint_matches_html_parser -q` — expected: FAIL (URL contains `bing.com` and `format=rss`, zero parsed results).

- [ ] **Step 3: Implement.** In `WebSearchTool.__init__` change the default and add an explicit params hook:

```python
def __init__(
    self,
    base_url: str = "https://html.duckduckgo.com/html/",
    timeout_seconds: float = 10,
    max_bytes: int = 500_000,
    extra_query_params: dict[str, str] | None = None,
) -> None:
    self.base_url = base_url
    self.timeout_seconds = timeout_seconds
    self.max_bytes = max_bytes
    self.extra_query_params = dict(extra_query_params or {})
```

In `search`, replace the URL construction:

```python
query_params = {"q": cleaned_query, **self.extra_query_params}
search_url = f"{self.base_url}?{urlencode(query_params)}"
```

Bing RSS remains available via `WebSearchTool(base_url="https://www.bing.com/search", extra_query_params={"format": "rss"})`. Search the repo for other `WebSearchTool(` constructions (`grep -rn "WebSearchTool(" src tests`) and leave RSS-dependent tests working by passing the explicit params where they relied on the old default.

- [ ] **Step 4: Run the web-search test group.** `uv run pytest tests/test_tools.py -q -k web_search` — expected: all PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "fix: point web search default endpoint at the HTML parser it ships"`

---

### Task 2: Safety-critic failure auditing + fail-closed option (spec item 8)

`_review_with_model` (`safety.py:438-469`) silently returns the deterministic decision on `LLMResponseError`. Also the critic never catches transport errors (`URLError`/`OSError` propagate). Fix: flag critic failures, and support `fail_closed` on safety policies.

**Files:**
- Modify: `src/code_scientist/safety.py` (`_review_with_model` ~438, `SafetyPolicy` dataclass + `load_safety_policies`, `review_goal_safety_with_model` ~135)
- Modify: `src/code_scientist/supervisor.py` (goal-safety call site, ~115)
- Test: `tests/test_safety_elo.py`

- [ ] **Step 1: Write the failing tests.**

```python
class ExplodingClient:
    def complete(self, prompt, max_tokens=0):
        raise LLMResponseError("model unavailable")


def test_safety_critic_failure_is_flagged_not_silent():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    decision = review_goal_safety_with_model(
        goal, llm_client=ExplodingClient(), max_tokens=64
    )
    assert decision.allowed is True  # deterministic fallback still allows
    assert "safety-critic-error" in decision.flags


def test_safety_critic_failure_fail_closed_blocks_for_manual_review():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    decision = review_goal_safety_with_model(
        goal, llm_client=ExplodingClient(), max_tokens=64, fail_closed=True
    )
    assert decision.allowed is False
    assert "manual-review-required" in decision.flags
    assert "safety-critic-error" in decision.flags
```

Match the actual signature of `review_goal_safety_with_model` at `safety.py:135` when writing the test (it may take policies; keep the new args keyword-only).

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_safety_elo.py -q -k critic_failure` — expected: FAIL (`TypeError: unexpected keyword 'fail_closed'` / missing flag).

- [ ] **Step 3: Implement.** In `_review_with_model`, catch broadly and mark:

```python
    except (LLMResponseError, OSError) as exc:
        error_flags = _unique([*deterministic.flags, "safety-critic-error"])
        if fail_closed:
            return SafetyDecision(
                allowed=False,
                reason=f"Safety critic unavailable ({exc}); blocked pending manual review.",
                flags=_unique([*error_flags, "manual-review-required"]),
            )
        return replace(deterministic, flags=error_flags)
```

Add `fail_closed: bool = False` keyword-only params threaded through `_review_with_model`, `review_goal_safety_with_model` (and the evidence/hypothesis `*_with_model` variants — same pattern). Add `fail_closed: bool = False` field to the `SafetyPolicy` dataclass with tolerant `from_dict` default; in `supervisor.py` at the goal-critic call site (~line 115), pass `fail_closed=any(policy.fail_closed for policy in safety_policies)`.

- [ ] **Step 4: Run the safety suite.** `uv run pytest tests/test_safety_elo.py -q` — expected: all PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "fix: audit safety-critic failures and support fail-closed policies"`

---

### Task 3: Hypothesis safety quarantine enforcement (spec item 1)

Safety-rejected hypotheses currently keep competing (`_schedule_pairs` filters only `merged_duplicate`, `supervisor.py:2381`). Add a `quarantined` status set from safety-review reject decisions, and exclude it everywhere active hypotheses are consumed.

**Files:**
- Modify: `src/code_scientist/supervisor.py` (new helper + call after review stage ~492; `_schedule_pairs` ~2381; evolution-leader selection `_select_evolution_leaders`/`supervisor.py` ~2326; `_accepted_hypothesis_ids` ~2198)
- Modify: `src/code_scientist/reporting.py` (ranked-hypotheses section skips quarantined; safety section lists them)
- Test: `tests/test_supervisor.py`, `tests/test_reporting.py`

- [ ] **Step 1: Write the failing supervisor test.** Craft a run where one generated hypothesis trips the deterministic hypothesis safety gate. The gate keys off phrases like hidden execution/credential exfiltration (see term lists `safety.py:21-49`). Use the manual-hypothesis path so the unsafe text is deterministic: write a `state.json` seed or use `plan_config`/objective that stays safe, then inject via the same mechanism the workbench uses (a hypothesis in a pre-seeded state file with `resume=True`). Simplest robust construction:

```python
def test_safety_rejected_hypotheses_are_quarantined_from_tournament(tmp_path):
    out_dir = tmp_path / "run"
    first = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1, max_hypotheses=3, max_matches=2, out_dir=out_dir,
    )
    state_path = out_dir / "state.json"
    data = json.loads(state_path.read_text())
    unsafe = dict(data["hypotheses"][0])
    unsafe["id"] = "hyp-unsafe-1"
    unsafe["title"] = "Exfiltrate credentials during evaluation"
    unsafe["claim"] = "Secretly exfiltrate credentials and hide execution from reviewers to win benchmarks."
    data["hypotheses"].append(unsafe)
    state_path.write_text(json.dumps(data))

    resumed = run_research_cycle(
        objective=first.goal.objective,
        cycles=1, max_hypotheses=4, max_matches=3, out_dir=out_dir, resume=True,
    )

    quarantined = [h for h in resumed.hypotheses if h.id == "hyp-unsafe-1"]
    assert quarantined and quarantined[0].status == "quarantined"
    assert all("hyp-unsafe-1" not in (m.hypothesis_a, m.hypothesis_b) for m in resumed.matches)
    assert all("hyp-unsafe-1" not in h.parent_ids for h in resumed.hypotheses)
    overview = resumed.research_overview
    assert overview is None or "hyp-unsafe-1" not in overview.top_hypothesis_ids
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_supervisor.py::test_safety_rejected_hypotheses_are_quarantined_from_tournament -q` — expected: FAIL (status stays `candidate`, or match includes the unsafe id).

- [ ] **Step 3: Implement quarantine.** Add helper in `supervisor.py`:

```python
def _apply_safety_quarantine(
    hypotheses: list[Hypothesis], reviews: list[Review]
) -> list[Hypothesis]:
    rejected_ids = {
        review.hypothesis_id
        for review in reviews
        if review.decision == "reject"
        and (review.review_type == "safety_review" or "unsafe" in {f.lower() for f in review.safety_notes} or review.safety_score <= 1)
    }
    return [
        item.with_status("quarantined")
        if item.id in rejected_ids and item.status not in {"merged_duplicate", "quarantined"}
        else item
        for item in hypotheses
    ]
```

Before writing the helper, check the actual `Review` field names (`decision`, `review_type`, `safety_score`, `safety_notes`) in `models.py` and use whichever combination actually signals a safety reject — the reflection agent scores safety 1 with decision "reject" (`agents.py:361-380`). Also quarantine at ingestion: where the supervisor loads pre-existing/manual hypotheses (state load path, ~`supervisor.py:206`), run `review_hypothesis_safety` on each and quarantine rejects.

Call `hypotheses = _apply_safety_quarantine(hypotheses, reviews)` immediately after the review stage completes (after `run_ready_cycle_tasks({task.id for task in review_tasks})`, ~line 492). Then exclude the status wherever active hypotheses are selected — define once:

```python
_INACTIVE_STATUSES = {"merged_duplicate", "quarantined"}
```

and update: `_schedule_pairs` (`item.status not in _INACTIVE_STATUSES`), evolution-leader selection, generation-allocation statistics, meta-review/overview top-id selection. Grep for `"merged_duplicate"` in `supervisor.py` and replace each membership test with `_INACTIVE_STATUSES` after checking the surrounding logic still makes sense (dedup-specific logic that genuinely means merged stays as-is).

- [ ] **Step 4: Run and pass.** `uv run pytest tests/test_supervisor.py::test_safety_rejected_hypotheses_are_quarantined_from_tournament -q` — expected: PASS.

- [ ] **Step 5: Write the failing reporting test.**

```python
def test_render_report_excludes_quarantined_from_rankings_and_lists_in_safety_section():
    state = _state_with_quarantined_hypothesis()  # build like neighboring reporting tests: minimal RunState with one accepted + one quarantined hypothesis
    report = render_report(state)
    ranked_section = report.split("## ")[_ranked_section_index]  # locate "Ranked Hypotheses" heading per existing test conventions
    assert "Quarantined" in report
    assert state.hypotheses[1].title not in ranked_section
    assert state.hypotheses[1].title in report  # visible in safety section
```

Use the existing state-builder fixtures in `tests/test_reporting.py` (they construct `RunState` directly); mirror their section-extraction style rather than the sketch above.

- [ ] **Step 6: Implement reporting.** In `reporting.py`, filter the ranked-hypotheses listing to exclude `status == "quarantined"`, and in the safety section (near the existing Safety Status/Evidence Safety Review rendering, ~`reporting.py:156, 416`) add a "Quarantined Hypotheses" subsection listing id, title, and the triggering review decision/flags.

- [ ] **Step 7: Run both suites.** `uv run pytest tests/test_supervisor.py tests/test_reporting.py -q` — expected: PASS (fix any existing tests that asserted rejected hypotheses appear ranked — update them to reflect intended behavior).

- [ ] **Step 8: Commit.** `git add -A && git commit -m "fix: quarantine safety-rejected hypotheses from tournament, evolution, and rankings"`

---

### Task 4: Consume adjusted scheduler weights (spec item 3a)

`_adjust_scheduler_weights` output is persisted in snapshots but `_task_priority` (`supervisor.py:3209`) reads only `plan.scheduler_weights`.

**Files:**
- Modify: `src/code_scientist/supervisor.py` (`_task_priority` ~3209, `score_task_priority` ~2640, call sites in `schedule_cycle_task` ~275)
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Write the failing test.**

```python
def test_task_priority_uses_latest_snapshot_adjusted_weights():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    plan = ResearchPlanConfig.from_goal(goal)
    snapshot_weights = dict(plan.scheduler_weights)
    snapshot_weights["generation"] = snapshot_weights.get("generation", 1.0) + 5.0
    snapshot = _make_context_snapshot(scheduler_weights=snapshot_weights)  # build via ContextSnapshot(...) with minimal fields like neighboring tests

    base = score_task_priority(plan, "generate", payload={}, hypotheses=[], reviews=[], matches=[], proximity_edges=[], user_feedback=[], context_snapshots=[])
    boosted = score_task_priority(plan, "generate", payload={}, hypotheses=[], reviews=[], matches=[], proximity_edges=[], user_feedback=[], context_snapshots=[snapshot])
    assert boosted > base
```

Read the real `score_task_priority` signature at `supervisor.py:2640` first and match it; add `context_snapshots` as a new keyword with default `None`.

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`TypeError: unexpected keyword 'context_snapshots'`).

- [ ] **Step 3: Implement.**

```python
def _effective_scheduler_weights(
    plan: ResearchPlanConfig, context_snapshots: list[ContextSnapshot] | None
) -> dict[str, float]:
    if context_snapshots:
        latest = context_snapshots[-1].scheduler_weights
        if latest:
            return dict(latest)
    return dict(plan.scheduler_weights)


def _task_priority(
    plan: ResearchPlanConfig,
    kind: str,
    context_snapshots: list[ContextSnapshot] | None = None,
) -> float:
    weights = _effective_scheduler_weights(plan, context_snapshots)
    weight_key = _task_weight_key(kind)
    return round(max(weights.get(weight_key, 1.0), 0.001), 3)
```

Thread `context_snapshots` through `score_task_priority` and every `schedule_cycle_task`/priority call inside `run_research_cycle` (the cycle body has the running `context_snapshots` list in scope — pass it). `rescore_task_queue`/`select_scheduler_task_pool` call sites get the same list.

- [ ] **Step 4: Run.** `uv run pytest tests/test_supervisor.py -q` — expected: PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "fix: task priorities consume snapshot-adjusted scheduler weights"`

---

### Task 5: Evaluate plan termination criteria (spec item 3b)

`termination_criteria` is parsed (`models.py:58,124`) but never evaluated; runs stop only on cycle count/wall time.

**Files:**
- Modify: `src/code_scientist/models.py` (`ContextSnapshot`: add `termination_reason: str = ""` with tolerant `from_dict` default)
- Modify: `src/code_scientist/supervisor.py` (new `evaluate_termination_criteria`; cycle-loop check in `run_research_cycle`; continuous-loop check in `run_continuous_research`)
- Test: `tests/test_models.py`, `tests/test_supervisor.py`

- [ ] **Step 1: Write the failing tests.**

```python
def test_context_snapshot_round_trips_termination_reason_and_defaults_old_state():
    snap_dict = _minimal_snapshot_dict()  # copy an existing round-trip test's dict
    restored = ContextSnapshot.from_dict(snap_dict)
    assert restored.termination_reason == ""
    snap_dict["termination_reason"] = "min_hypotheses:2"
    assert ContextSnapshot.from_dict(snap_dict).termination_reason == "min_hypotheses:2"


def test_run_terminates_early_when_min_hypotheses_criterion_met(tmp_path):
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    plan = ResearchPlanConfig.from_goal(goal, termination_criteria=["min_hypotheses: 2"])
    state = run_research_cycle(
        objective=goal.objective, cycles=5, max_hypotheses=4, max_matches=1,
        out_dir=tmp_path / "run", plan_config=plan,
    )
    assert len(state.context_snapshots) < 5
    assert state.context_snapshots[-1].termination_reason.startswith("min_hypotheses")
```

Check `ResearchPlanConfig.from_goal`'s actual keyword for termination criteria (`models.py:136`) and adjust.

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (5 snapshots, empty reason).

- [ ] **Step 3: Implement.**

```python
def evaluate_termination_criteria(
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    context_snapshots: list[ContextSnapshot],
) -> str | None:
    active = [h for h in hypotheses if h.status not in _INACTIVE_STATUSES]
    for criterion in plan.termination_criteria:
        text = criterion.lower().strip()
        if text.startswith("min_hypotheses") or "at least" in text:
            digits = [int(part) for part in re.findall(r"\d+", text)]
            target = digits[0] if digits else None
            if target is not None and len(active) >= target:
                return f"min_hypotheses:{target}"
        elif text.startswith("elo_plateau") or "elo plateau" in text:
            digits = [int(part) for part in re.findall(r"\d+", text)]
            window = digits[0] if digits else 2
            best_by_cycle = [
                max((h.elo for h in hypotheses), default=0.0)
            ]  # current cycle best; prior bests come from snapshots' top ids — instead track via snapshot count:
            if len(context_snapshots) >= window:
                recent = context_snapshots[-window:]
                bests = {tuple(snap.top_hypothesis_ids[:1]) for snap in recent}
                if len(bests) == 1 and bests != {tuple()}:
                    return f"elo_plateau:{window}"
        elif text.startswith("all_reviewed") or "all reviewed" in text:
            reviewed_ids = {review.hypothesis_id for review in reviews}
            if active and all(h.id in reviewed_ids for h in active):
                return "all_reviewed"
    return None
```

Note the plateau check uses "same top hypothesis for N consecutive snapshots" as the deterministic stand-in for best-Elo-unchanged (top ids are already persisted; storing float histories is Wave 2's Elo-history work). Delete the unused `best_by_cycle` line — shown here only to flag the design decision. **Important:** the default plan's `termination_criteria` is `["max_cycles", "max_hypotheses", "human_stop"]` (`models.py:196`) — those strings match no branch above and so never terminate early; add them to an explicit ignore set so they're not reported as unevaluated. Unrecognized criteria: collect and record `"unevaluated:<text>"` in the snapshot's `next_actions` (no new field needed).

In `run_research_cycle`'s cycle loop, after the snapshot is built, evaluate; when a reason is returned, rebuild the final snapshot with `termination_reason=reason` (use `dataclasses.replace`) and `break`. In `run_continuous_research`, stop the polling loop when the latest snapshot carries a non-empty `termination_reason`.

- [ ] **Step 4: Run.** `uv run pytest tests/test_models.py tests/test_supervisor.py -q` — expected: PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: evaluate plan termination criteria and record termination reason"`

---

### Task 6: Rank-tiered debate depth (spec item 4)

`_use_multi_round_debate(plan)` (`supervisor.py:2188`) is plan-global and defaults off; the paper tiers debate depth by rank.

**Files:**
- Modify: `src/code_scientist/supervisor.py` (ranking stage ~581-655, `_use_multi_round_debate` ~2188)
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Write the failing test.**

```python
def test_top_tier_pairs_use_multi_round_debate_and_others_single_turn(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=2, max_hypotheses=8, max_matches=6, out_dir=tmp_path / "run",
    )
    assert state.matches, "expected matches"
    tiers = {m.id: ("multi_round" in (m.comparison_mode or "")) for m in state.matches}
    elo_by_id = {h.id: h.elo for h in state.hypotheses}
    ranked = sorted(elo_by_id, key=lambda hid: elo_by_id[hid], reverse=True)
    tier_size = max(2, len(ranked) // 4)
    top = set(ranked[:tier_size])
    multi = [m for m in state.matches if tiers[m.id]]
    single = [m for m in state.matches if not tiers[m.id]]
    assert multi, "expected at least one top-tier multi-round match"
    assert single, "expected at least one single-turn match"
    assert "debate_tier=top" in multi[0].judge_trace
```

Check `Match`'s field for comparison mode in `models.py` (~196) — use the real field name; if none exists, assert on `judge_trace` containing `debate_tier=top` / `debate_tier=standard` only. Note tiering is decided against Elo **at match time**, not final Elo, so assert structurally (both kinds exist + trace marker) rather than exact pair membership.

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (no multi-round matches by default).

- [ ] **Step 3: Implement.** In the ranking stage (~581), replace the single global flag with per-pair tiering:

```python
override = _debate_depth_override(plan)  # "multi" | "single" | None
active = [h for h in hypotheses if h.status not in _INACTIVE_STATUSES]
ranked_ids = [h.id for h in sorted(active, key=lambda h: h.elo, reverse=True)]
tier_size = max(2, len(ranked_ids) // 4)
top_tier = set(ranked_ids[:tier_size])
for first, second in _schedule_pairs(...):
    pair_is_top = first.id in top_tier and second.id in top_tier
    use_multi = override == "multi" or (override is None and pair_is_top)
    ...
```

Rename/extend `_use_multi_round_debate` into:

```python
def _debate_depth_override(plan: ResearchPlanConfig) -> str | None:
    signals = [*plan.generation_methods, *plan.review_types, *plan.allowed_tools]
    normalized = {signal.lower().replace("-", "_") for signal in signals}
    if {"single_turn_debate", "single_round_debate"} & normalized:
        return "single"
    if {"simulated_debate", "multi_round_debate", "multi_turn_debate"} & normalized:
        return "multi"
    return None
```

Append `debate_tier=top` / `debate_tier=standard` to each match's `judge_trace` and record the per-match mode in the ranking task trace notes (replacing the cycle-global `action`/`comparison_label` at ~614 with per-pair labels). Update any existing tests that assumed plan-level simulated-debate signals produce all-multi-round — the override preserves that, so most should pass unchanged.

- [ ] **Step 4: Run.** `uv run pytest tests/test_supervisor.py -q` — expected: PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: tier tournament debate depth by Elo rank per the paper"`

---

### Task 7: Meta-review feedback into agent prompts, not post-hoc artifacts (spec item 2)

Feedback currently mutates finished artifacts (`_apply_generation_feedback` `supervisor.py:1635`, `_apply_review_feedback` ~1725, `_apply_match_feedback` ~1741, `_apply_proximity_feedback` ~1754, `_apply_overview_feedback` ~1768); only Evolution's prompt receives feedback.

**Files:**
- Modify: `src/code_scientist/agents.py` (`_generation_prompt` ~3661, `_review_prompt` ~2413, `_ranking_prompt` ~2583, proximity prompt builders; `GenerationAgent.generate`/`generate_with_mode`, `ReflectionAgent.review_with_type`, `RankingAgent.compare_debate`/`compare_multi_round_debate`, `ProximityAgent` LLM path — add `agent_feedback: list[str] | None = None` parameters)
- Modify: `src/code_scientist/supervisor.py` (pass `_agent_feedback_for(...)` into agent calls; delete the five `_apply_*_feedback` helpers and their call sites, keeping trace-note mentions)
- Test: `tests/test_supervisor.py`, `tests/test_agents.py` if present (else `tests/test_supervisor.py`)

- [ ] **Step 1: Write the failing test.** Use a recording fake client (mirror the existing fake-provider pattern used by `test_supervisor_anthropic_provider_drives_plan_and_all_agent_roles`):

```python
def test_meta_review_feedback_reaches_agent_prompts_not_artifacts(tmp_path):
    out_dir = tmp_path / "run"
    recorder = RecordingFakeClient()  # reuse/extend the existing fake provider client that returns schema-valid JSON and records prompts
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=2, max_hypotheses=4, max_matches=2, out_dir=out_dir,
        llm_client=recorder, provider="anthropic",
    )
    feedback_terms = [
        text for meta in state.meta_reviews for text in meta.agent_feedback.get("generation", [])
    ]
    assert feedback_terms, "expected generation-scoped meta-review feedback after cycle 1"
    cycle2_generation_prompts = [p for p in recorder.prompts_for("generation") if "Meta-review feedback" in p]
    assert cycle2_generation_prompts, "cycle-2 generation prompt must embed meta-review feedback"
    assert all(
        "Meta-review feedback for generation" not in h.rationale for h in state.hypotheses
    ), "artifacts must not be post-hoc annotated with feedback strings"
    assert all(
        not any(f.startswith("Meta-review feedback for") for f in r.findings)
        for r in state.reviews
    )
```

Check `MetaReview`'s real field for agent feedback (`agent_feedback` dict vs list) in `models.py` and how the existing fake client is structured; extend it minimally to record prompts (a list attribute + labeling by which prompt template matched is fine — match on distinctive prompt prefixes).

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (prompts lack the block; artifacts carry injected strings).

- [ ] **Step 3: Implement prompt threading.** Shared helper in `agents.py`:

```python
def _feedback_block(agent_feedback: list[str] | None) -> str:
    if not agent_feedback:
        return ""
    lines = "\n".join(f"- {item}" for item in agent_feedback)
    return f"\n\nMeta-review feedback from prior cycles (address these):\n{lines}\n"
```

Append `_feedback_block(agent_feedback)` to `_generation_prompt`, `_review_prompt`, `_ranking_prompt`, and the proximity LLM prompt(s); add the parameter to each agent entry point and pass it down to the prompt builders (deterministic paths accept and record it in traces but do not mutate artifact content). Deterministic conditioning per spec: in `GenerationAgent.generate`, when `agent_feedback` names weakness terms, skip candidate blueprints whose claim contains any feedback term (case-insensitive substring over terms longer than 4 chars) before applying `limit`; in `ReflectionAgent`, when the hypothesis text itself contains a feedback term, add a finding `f"Prior meta-review flagged: {term}"` (grounded in the hypothesis, not blanket annotation).

- [ ] **Step 4: Remove post-hoc mutation.** In `supervisor.py`, delete `_apply_generation_feedback`, `_apply_review_feedback`, `_apply_match_feedback`, `_apply_proximity_feedback`, `_apply_overview_feedback` and rewire their call sites to pass `agent_feedback` into the agent invocations instead. Keep the existing trace notes ("Agent feedback: …"). Fix compile errors from removed helpers.

- [ ] **Step 5: Run and fix fallout.** `uv run pytest tests/test_supervisor.py -q` then the full `uv run pytest -q`. Existing tests asserting on injected strings (search: `grep -rn "Meta-review feedback for" tests/`) must be updated to assert the new behavior (feedback in prompts/trace notes, not artifacts). Expected: all PASS.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "fix: thread meta-review feedback into agent prompts instead of post-hoc artifact edits"`

---

### Task 8: Honest feedback-loop metric — weakness recurrence (spec item 2, metric)

`_build_feedback_loop_evaluation` (`supervisor.py:~1790`) currently detects the very strings Task 7 just stopped injecting; replace with weakness-recurrence measurement.

**Files:**
- Modify: `src/code_scientist/supervisor.py` (`_build_feedback_loop_evaluation` and its helpers)
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Write the failing test.**

```python
def test_feedback_loop_evaluation_measures_weakness_recurrence(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=3, max_hypotheses=4, max_matches=2, out_dir=tmp_path / "run",
    )
    records = state.feedback_loop_evaluations
    assert records, "expected proxy feedback-loop records"
    latest = records[-1]
    assert "weakness_recurrence_before" in latest.baseline_quality
    assert "weakness_recurrence_after" in latest.observed_quality
    assert 0.0 <= latest.baseline_quality["weakness_recurrence_before"] <= 1.0
```

Read `FeedbackLoopEvaluation`'s real field names in `models.py` (~679: it has `measurement_status`, likely `baseline_quality`/`observed_quality` dicts — match them exactly).

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (metric keys absent).

- [ ] **Step 3: Implement.**

```python
def _weakness_terms(meta: MetaReview) -> set[str]:
    terms: set[str] = set()
    for text in [*getattr(meta, "common_weaknesses", []), *[fb for items in _all_agent_feedback(meta) for fb in items]]:
        terms.update(token for token in re.findall(r"[a-z]{5,}", text.lower()))
    return terms - _FEEDBACK_STOPWORDS  # small stopword set: {"hypothesis", "review", "should", "improve", ...}


def _weakness_recurrence_rate(terms: set[str], reviews: list[Review]) -> float:
    if not terms or not reviews:
        return 0.0
    hits = sum(
        1 for review in reviews
        if any(term in " ".join([*review.weaknesses, *review.findings]).lower() for term in terms)
    )
    return round(hits / len(reviews), 3)
```

In `_build_feedback_loop_evaluation`, compute `before = _weakness_recurrence_rate(terms, prior_cycle_reviews)` and `after = _weakness_recurrence_rate(terms, current_cycle_reviews)`, mapping reviews to cycles via the agent traces that reference them (`AgentTrace.cycle` + `output_refs`) — build `review_cycle = {ref: trace.cycle for trace in agent_traces if trace.agent == "reflection" for ref in trace.output_refs}`. Store both rates in the record's quality dicts; drop the injected-string adoption counting. Check `Review` field names (`weaknesses`, `findings`) before writing.

- [ ] **Step 4: Run.** `uv run pytest tests/test_supervisor.py -q` — expected: PASS (update any test asserting the old adoption fields).

- [ ] **Step 5: Commit.** `git add -A && git commit -m "fix: measure feedback efficacy as weakness recurrence, not injected-string detection"`

---

### Task 9: De-stub research expansion and recurrent tournament review (spec item 5)

`research_expansion_from_meta_review` re-tags `generate()` (`agents.py:212-217`); `recurrent_tournament_review` relabels an initial review (`agents.py:475-481`).

**Files:**
- Modify: `src/code_scientist/agents.py` (`generate_with_mode` signature + expansion branch; `review_with_type` signature + tournament branch; LLM prompt additions)
- Modify: `src/code_scientist/supervisor.py` (pass existing hypotheses/overview into the generation call; pass matches/prior reviews into review calls)
- Test: `tests/test_supervisor.py` (or `tests/test_agents.py` if that's where agent-mode tests live — check `grep -rln "generate_with_mode" tests/`)

- [ ] **Step 1: Write the failing tests.**

```python
def test_research_expansion_targets_unexplored_areas():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    agent = GenerationAgent()
    baseline = agent.generate_with_mode(goal, [], "paper_seeded_idea_generation", limit=6)
    existing = baseline[:3]
    expanded = agent.generate_with_mode(
        goal, [], "research_expansion_from_meta_review", limit=3,
        existing_hypotheses=existing,
    )
    existing_claims = {h.claim for h in existing}
    assert expanded
    assert all(h.claim not in existing_claims for h in expanded)
    assert all("unexplored" in h.rationale.lower() or "expansion" in h.origin for h in expanded)


def test_recurrent_tournament_review_cites_match_record():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    agent = ReflectionAgent()
    hypothesis = GenerationAgent().generate(goal, [], limit=1)[0]
    matches = [_make_match(winner=hypothesis.id, loser="hyp-other")] * 2  # build Match(...) minimally like neighboring tests
    review = agent.review_with_type(
        goal, hypothesis, "recurrent_tournament_review", matches=matches,
    )
    assert review.review_type == "recurrent_tournament_review"
    assert any("2" in f and ("won" in f.lower() or "match" in f.lower()) for f in review.findings)
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`TypeError` for new keywords).

- [ ] **Step 3: Implement expansion.** In `generate_with_mode`, add keyword-only `existing_hypotheses: list[Hypothesis] | None = None, research_overview: Any | None = None` and replace the expansion branch:

```python
if mode == "research_expansion_from_meta_review":
    source_evidence = evidence.evidence if isinstance(evidence, EvidenceStore) else evidence
    known = existing_hypotheses or []
    known_tokens = {
        token for item in known for token in re.findall(r"[a-z]{5,}", f"{item.title} {item.claim}".lower())
    }
    overview_note = ""
    if research_overview is not None:
        overview_note = f" Overview gaps considered: {'; '.join(research_overview.limitations[:2])}." if research_overview.limitations else ""
    candidates = self.generate(goal, source_evidence, limit=limit * 3)
    known_claims = {item.claim for item in known}
    fresh = [
        item for item in candidates
        if item.claim not in known_claims
        and len(known_tokens & set(re.findall(r"[a-z]{5,}", item.claim.lower()))) <= 2
    ] or [item for item in candidates if item.claim not in known_claims]
    return [
        replace(
            item,
            id=stable_id("hyp", f"{goal.id}:expansion:{item.id}"),
            origin="generation:research_expansion_from_meta_review",
            rationale=f"{item.rationale} Targets unexplored area relative to {len(known)} existing hypotheses.{overview_note}",
        )
        for item in fresh[:limit]
    ]
```

LLM path: when `self.llm_client` is set, include existing titles + overview summary in the generation prompt with an instruction to target unexplored areas (extend `_generation_prompt` with an optional `expansion_context: str` block).

- [ ] **Step 4: Implement tournament review.** In `review_with_type`, add keyword-only `matches: list[Match] | None = None, prior_reviews: list[Review] | None = None` and replace the branch:

```python
if review_type == "recurrent_tournament_review":
    base = self.review(goal, hypothesis)
    record = [m for m in (matches or []) if hypothesis.id in (m.hypothesis_a, m.hypothesis_b)]
    wins = sum(1 for m in record if m.winner == hypothesis.id)
    losses = sum(1 for m in record if m.winner and m.winner != hypothesis.id)
    recurring = _recurring_weakness_terms(prior_reviews or [], hypothesis.id)
    findings = [
        *base.findings,
        f"Tournament record: won {wins} and lost {losses} of {len(record)} matches.",
    ]
    if recurring:
        findings.append(f"Recurring weaknesses across prior reviews: {', '.join(sorted(recurring)[:3])}.")
    return replace(
        base,
        id=stable_id("rev", f"{goal.id}:{hypothesis.id}:{review_type}:{wins}:{losses}"),
        review_type=review_type,
        findings=findings,
    )
```

with helper:

```python
def _recurring_weakness_terms(prior_reviews: list[Review], hypothesis_id: str) -> set[str]:
    counts: Counter[str] = Counter()
    for review in prior_reviews:
        if review.hypothesis_id != hypothesis_id:
            continue
        for weakness in review.weaknesses:
            counts.update(re.findall(r"[a-z]{5,}", weakness.lower()))
    return {term for term, count in counts.items() if count >= 2}
```

Check `Match` field names (`hypothesis_a`, `hypothesis_b`, `winner`) and `Review.weaknesses` in `models.py` first. In `supervisor.py`, pass `matches=matches, prior_reviews=reviews` through `_review_for_plan` into `review_with_type`, and `existing_hypotheses=hypotheses, research_overview=<latest overview or None>` into the expansion-mode generation call. LLM path for the review includes a one-line match summary in `_review_prompt`.

- [ ] **Step 5: Run.** `uv run pytest tests/test_supervisor.py -q` (plus agent test file if used) — expected: PASS.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: research expansion targets unexplored areas; tournament review cites match record"`

---

### Task 10: Bounded review-stage concurrency (spec item 6)

`run_task_worker` supports `max_concurrency` (`supervisor.py:2950`) but every supervisor call uses the default 1. Enable it for the per-hypothesis review pool only, with a lock around shared-state mutation.

**Files:**
- Modify: `src/code_scientist/supervisor.py` (`run_research_cycle` signature + review stage ~479-492, `run_ready_cycle_tasks` ~317)
- Modify: `src/code_scientist/cli.py` (`--review-concurrency` option forwarded to `run_research_cycle`)
- Test: `tests/test_supervisor.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test.**

```python
def test_review_stage_runs_with_bounded_concurrency(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1, max_hypotheses=4, max_matches=2, out_dir=tmp_path / "run",
        review_concurrency=2,
    )
    review_tasks = [t for t in state.task_queue if t.kind.startswith("review")]
    assert review_tasks and all(t.status == "completed" for t in review_tasks)
    task_ids = [t.id for t in state.task_queue]
    assert len(task_ids) == len(set(task_ids)), "no duplicated task records"
    assert state.reviews, "reviews still produced"
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`TypeError: unexpected keyword 'review_concurrency'`).

- [ ] **Step 3: Implement.** Add `review_concurrency: int = 1` to `run_research_cycle` (default 1 keeps current behavior; the CLI default can be 1 too — opt-in). Extend the inner `run_ready_cycle_tasks(eligible_task_ids, max_concurrency=1)` to forward to `run_task_worker(..., max_concurrency=max_concurrency)`, and call the review stage with `run_ready_cycle_tasks({task.id for task in review_tasks}, max_concurrency=max(1, min(review_concurrency, len(review_tasks))))`. Guard shared mutation: create `state_lock = threading.Lock()` in the cycle scope and wrap the body of each review-task `execute` closure's state-mutating tail (appends to `reviews`, `agent_traces`, `retrieval_memory`) in `with state_lock:`. The LLM/evidence retrieval work stays outside the lock. `run_task_worker` already persists once after the concurrent pool completes — verify `persist_current_task_state` isn't also called inside the review execute closures (if it is, move it out).

- [ ] **Step 4: CLI flag.** In `cli.py`, add `--review-concurrency` (int, default 1) to the `run` subcommand, forward it, and add a CLI test following the pattern of existing flag-forwarding tests:

```python
def test_cli_run_accepts_review_concurrency(tmp_path, monkeypatch):
    captured = {}
    def fake_run(**kwargs):
        captured.update(kwargs)
        return _minimal_state()  # same stub neighboring CLI tests use
    monkeypatch.setattr("code_scientist.cli.run_research_cycle", fake_run)
    main(["run", "goal text", "--out", str(tmp_path), "--review-concurrency", "3"])
    assert captured["review_concurrency"] == 3
```

- [ ] **Step 5: Run.** `uv run pytest tests/test_supervisor.py tests/test_cli.py -q` — expected: PASS.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: bounded concurrency for per-hypothesis review tasks"`

---

### Task 11: Full verification and audit-doc update

**Files:**
- Modify: `docs/paper-alignment-audit-2026-07-04.md` (mark Wave 1 items resolved)
- Test: everything

- [ ] **Step 1: Full Python suite.** `uv run pytest -q` — expected: all PASS (≥303 tests, plus the new ones).
- [ ] **Step 2: Web suite + typecheck.** `cd web && PATH=/opt/homebrew/bin:$PATH npm test && npm run typecheck` — expected: PASS (web code untouched; `types.ts` needs no change since `termination_reason`/`quarantined` arrive as plain JSON fields — verify `RunInsights`/`Workbench` don't crash on them by running the tests).
- [ ] **Step 3: Smoke run.** `uv run code-scientist run "Find testable ideas that could improve LLM coding agents" --cycles 2 --max-hypotheses 6 --max-matches 4 --out runs/wave1-smoke` — verify report renders, matches carry `debate_tier=` markers, snapshot has scheduler weights, no quarantined section (safe goal).
- [ ] **Step 4: Update the audit doc.** In `docs/paper-alignment-audit-2026-07-04.md`, annotate defects 1-7 and the two de-stubbed mechanisms with "resolved in Wave 1 (`feature/paper-alignment-wave1`)".
- [ ] **Step 5: Commit.** `git add -A && git commit -m "docs: mark wave 1 core-loop fidelity items resolved in alignment audit"`
