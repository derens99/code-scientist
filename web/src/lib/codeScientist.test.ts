import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  appendManualHypothesis,
  appendManualReview,
  appendUserFeedback,
  applyProximityClusterOverride,
  applyProximityOverride,
  applyRunCommand,
  buildRunArgs,
  buildEvaluationReturnArgs,
  buildSourceAttachmentArgs,
  clampInteger,
  listRuns,
  sanitizeRunName,
  updateRunGuidance,
  writeRunControl
} from "./codeScientist";

const originalRoot = process.env.CODE_SCIENTIST_ROOT;
let tempRoot: string | null = null;

afterEach(async () => {
  if (tempRoot) {
    await rm(tempRoot, { recursive: true, force: true });
    tempRoot = null;
  }
  if (originalRoot === undefined) {
    delete process.env.CODE_SCIENTIST_ROOT;
  } else {
    process.env.CODE_SCIENTIST_ROOT = originalRoot;
  }
});

describe("sanitizeRunName", () => {
  it("keeps run output names inside the runs directory", () => {
    expect(sanitizeRunName("../Bad Run!")).toBe("bad-run");
    expect(sanitizeRunName("demo_final.01")).toBe("demo_final.01");
  });

  it("uses a generated fallback for empty names", () => {
    expect(sanitizeRunName("   ")).toMatch(/^ui-run-\d+$/);
  });
});

describe("clampInteger", () => {
  it("clamps numeric input to the configured range", () => {
    expect(clampInteger(12.8, 1, 10, 3)).toBe(10);
    expect(clampInteger(-1, 1, 10, 3)).toBe(1);
    expect(clampInteger("4", 1, 10, 3)).toBe(4);
    expect(clampInteger("not-a-number", 1, 10, 3)).toBe(3);
  });
});

describe("listRuns", () => {
  it("returns readable run summaries sorted newest first", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    const older = path.join(root, "runs", "older");
    const newer = path.join(root, "runs", "newer");
    await mkdir(older, { recursive: true });
    await mkdir(newer, { recursive: true });
    await writeFile(path.join(older, "state.json"), JSON.stringify(runState("Older objective")), "utf8");
    await new Promise((resolve) => setTimeout(resolve, 5));
    await writeFile(path.join(newer, "state.json"), JSON.stringify(runState("Newer objective")), "utf8");
    await writeFile(path.join(newer, "report.md"), "# Report", "utf8");

    const runs = await listRuns();

    expect(runs.map((run) => run.id)).toEqual(["newer", "older"]);
    expect(runs[0]).toMatchObject({
      objective: "Newer objective",
      runStatus: "running",
      hypothesisCount: 1,
      reviewCount: 1,
      matchCount: 1,
      safetyAllowed: true,
      readable: true
    });
    expect(runs[0].reportPath).toContain("report.md");
  });
});

describe("buildRunArgs", () => {
  it("includes continuous supervisor flags when requested", () => {
    const args = buildRunArgs({
      objective: "Research non-transformer laptop LLMs",
      cycles: 1,
      maxHypotheses: 6,
      maxMatches: 4,
      runName: "continuous-demo",
      provider: "anthropic",
      continuous: true,
      intervalSeconds: 5,
      maxWallMinutes: 30
    });

    expect(args).toEqual([
      "run",
      "code-scientist",
      "run",
      "Research non-transformer laptop LLMs",
      "--cycles",
      "1",
      "--max-hypotheses",
      "6",
      "--max-matches",
      "4",
      "--provider",
      "anthropic",
      "--continuous",
      "--interval-seconds",
      "5",
      "--max-wall-minutes",
      "30",
      "--out",
      path.join("runs", "continuous-demo")
    ]);
  });

  it("includes selected evidence, repository search, web evidence, and literature search sources", () => {
    const args = buildRunArgs({
      objective: "Research repo-grounded coding-agent ideas",
      cycles: 1,
      maxHypotheses: 6,
      maxMatches: 4,
      runName: "source-demo",
      provider: "deterministic",
      continuous: false,
      goalBriefPaths: ["/tmp/goal-brief.md", " ", "/tmp/lab-constraints.md"],
      safetyPolicyPaths: ["/tmp/safety-policy.json", " ", "/tmp/org-policy.json"],
      evidencePaths: ["/tmp/evidence.md", " ", "/tmp/prior-state.json"],
      evidenceIndexPaths: ["/tmp/corpus.index.json", " ", "/tmp/prior-corpus.index.json"],
      repoSearchPaths: ["/tmp/repo", "/tmp/repo-2"],
      webEvidenceUrls: ["https://example.test/paper", " ", "https://example.test/survey"],
      webCrawlDepth: 1,
      webSearchQueries: ["coding agent benchmark", " ", "agent memory"],
      webSearchFetch: true,
      webSearchCrawlDepth: 1,
      literatureSearchQueries: ["coding agent benchmark", " ", "LLM repair evaluation"],
      literatureFullText: true,
      capabilityEvaluationPaths: ["/tmp/capability.json", " ", "/tmp/human-scores.json"],
      preferenceReviewPaths: ["/tmp/preference.json", " ", "/tmp/preference-review.json"],
      prospectiveEvaluationPaths: ["/tmp/prospective.json", " ", "/tmp/external-validation.json"],
      feedbackLoopEvaluationPaths: ["/tmp/feedback-loop.json", " ", "/tmp/external-feedback.json"],
      feedbackLoopReviewPaths: ["/tmp/blind-review.json", " ", "/tmp/reviewer-scores.json"]
    });

    expect(args).toContain("--goal-brief");
    expect(args).toContain("/tmp/goal-brief.md");
    expect(args).toContain("/tmp/lab-constraints.md");
    expect(args).toContain("--safety-policy");
    expect(args).toContain("/tmp/safety-policy.json");
    expect(args).toContain("/tmp/org-policy.json");
    expect(args).toContain("--evidence-path");
    expect(args).toContain("/tmp/evidence.md");
    expect(args).toContain("/tmp/prior-state.json");
    expect(args).toContain("--evidence-index");
    expect(args).toContain("/tmp/corpus.index.json");
    expect(args).toContain("/tmp/prior-corpus.index.json");
    expect(args).toContain("--repo-search-path");
    expect(args).toContain("/tmp/repo");
    expect(args).toContain("/tmp/repo-2");
    expect(args).toContain("--web-evidence-url");
    expect(args).toContain("https://example.test/paper");
    expect(args).toContain("https://example.test/survey");
    expect(args).toContain("--web-crawl-depth");
    expect(args).toContain("1");
    expect(args).toContain("--web-search-query");
    expect(args).toContain("coding agent benchmark");
    expect(args).toContain("agent memory");
    expect(args).toContain("--web-search-fetch");
    expect(args).toContain("--web-search-crawl-depth");
    expect(args).toContain("1");
    expect(args).toContain("--literature-search-query");
    expect(args).toContain("coding agent benchmark");
    expect(args).toContain("LLM repair evaluation");
    expect(args).toContain("--literature-full-text");
    expect(args).toContain("--capability-eval-fixture");
    expect(args).toContain("/tmp/capability.json");
    expect(args).toContain("/tmp/human-scores.json");
    expect(args).toContain("--preference-review-fixture");
    expect(args).toContain("/tmp/preference.json");
    expect(args).toContain("/tmp/preference-review.json");
    expect(args).toContain("--prospective-eval-fixture");
    expect(args).toContain("/tmp/prospective.json");
    expect(args).toContain("/tmp/external-validation.json");
    expect(args).toContain("--feedback-loop-eval-fixture");
    expect(args).toContain("/tmp/feedback-loop.json");
    expect(args).toContain("/tmp/external-feedback.json");
    expect(args).toContain("--feedback-loop-review-fixture");
    expect(args).toContain("/tmp/blind-review.json");
    expect(args).toContain("/tmp/reviewer-scores.json");
    expect(args).not.toContain(" ");
  });
});

describe("buildEvaluationReturnArgs", () => {
  it("builds a run-scoped append command for returned evaluation packet paths", () => {
    const args = buildEvaluationReturnArgs("paper-study-demo", {
      capabilityEvaluationPaths: ["/tmp/capability.json", " "],
      capabilityReviewPaths: ["/tmp/capability-review.json"],
      preferenceReviewPaths: ["/tmp/preference-review.json"],
      prospectiveEvaluationPaths: ["/tmp/prospective.json"],
      feedbackLoopEvaluationPaths: ["/tmp/feedback-loop.json"],
      feedbackLoopReviewPaths: ["/tmp/feedback-loop-review.json", " "]
    });

    expect(args).toEqual([
      "run",
      "code-scientist",
      "evaluation-return",
      path.join("runs", "paper-study-demo"),
      "--capability-eval-fixture",
      "/tmp/capability.json",
      "--capability-review-fixture",
      "/tmp/capability-review.json",
      "--preference-review-fixture",
      "/tmp/preference-review.json",
      "--prospective-eval-fixture",
      "/tmp/prospective.json",
      "--feedback-loop-eval-fixture",
      "/tmp/feedback-loop.json",
      "--feedback-loop-review-fixture",
      "/tmp/feedback-loop-review.json"
    ]);
  });
});

describe("buildSourceAttachmentArgs", () => {
  it("builds a run-scoped append command for source attachment paths", () => {
    const args = buildSourceAttachmentArgs("paper-study-demo", {
      evidencePaths: ["/tmp/notes.md", " ", "/tmp/repo"],
      evidenceIndexPaths: ["/tmp/corpus.index.json"]
    });

    expect(args).toEqual([
      "run",
      "code-scientist",
      "source-attachment",
      path.join("runs", "paper-study-demo"),
      "--evidence-path",
      "/tmp/notes.md",
      "--evidence-path",
      "/tmp/repo",
      "--evidence-index",
      "/tmp/corpus.index.json"
    ]);
  });
});

describe("writeRunControl", () => {
  it("writes pause, resume, and stop actions inside the run directory", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    await mkdir(path.join(root, "runs", "continuous-demo"), { recursive: true });

    await writeRunControl("continuous-demo", "pause");
    let control = JSON.parse(await readFile(path.join(root, "runs", "continuous-demo", "control.json"), "utf8"));
    expect(control.action).toBe("pause");

    await writeRunControl("continuous-demo", "resume");
    control = JSON.parse(await readFile(path.join(root, "runs", "continuous-demo", "control.json"), "utf8"));
    expect(control.action).toBe("run");
  });
});

describe("human run inputs", () => {
  it("persists structured feedback, manual hypotheses, and manual reviews", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    const runDir = path.join(root, "runs", "human-loop");
    await mkdir(runDir, { recursive: true });
    await writeFile(path.join(runDir, "state.json"), JSON.stringify(runState("Human loop")), "utf8");

    const feedbackState = await appendUserFeedback("human-loop", {
      targetId: "hyp-1",
      kind: "verification_request",
      influence: "scheduler_boost",
      content: "Verify this against a maintainer-labeled benchmark."
    });
    expect(feedbackState.user_feedback?.[0]).toMatchObject({
      kind: "verification_request",
      target_id: "hyp-1",
      influence: "scheduler_boost",
      content: "Verify this against a maintainer-labeled benchmark."
    });

    const hypothesisState = await appendManualHypothesis("human-loop", {
      title: "Maintainer replay memory",
      claim: "Using maintainer review replays will improve patch selection.",
      rationale: "Review replays expose failure modes the generator misses.",
      assumptions: ["Review traces are available."],
      evidenceRefs: ["ev-review"],
      experiment: "Compare replay-seeded and baseline repair runs.",
      metrics: ["pass_rate", "regression_count"],
      successCondition: "Higher pass rate without extra regressions.",
      risks: ["Overfits one maintainer style."]
    });
    const manualHypothesis = hypothesisState.hypotheses.find((hypothesis) => hypothesis.origin === "human");
    expect(manualHypothesis).toMatchObject({
      title: "Maintainer replay memory",
      status: "candidate",
      evidence_refs: ["ev-review"],
      test_plan: {
        experiment: "Compare replay-seeded and baseline repair runs.",
        metrics: ["pass_rate", "regression_count"],
        success_condition: "Higher pass rate without extra regressions."
      }
    });

    const reviewState = await appendManualReview("human-loop", {
      hypothesisId: manualHypothesis?.id ?? "missing",
      decision: "revise",
      strengths: ["Concrete evaluation target."],
      weaknesses: ["Needs cost estimate."],
      safetyNotes: ["Local-only traces."],
      findings: ["No benchmark result yet."],
      evidenceRefs: ["ev-review"],
      confidence: 0.7,
      requiresRevision: true
    });
    const manualReview = reviewState.reviews.find((review) => review.hypothesis_id === manualHypothesis?.id);
    expect(manualReview).toMatchObject({
      decision: "revise",
      review_type: "manual_review",
      findings: ["No benchmark result yet."],
      requires_revision: true
    });

    const guidanceState = await updateRunGuidance("human-loop", {
      preferences: ["Prefer low-cost local experiments."],
      constraints: ["Do not use external services."],
      allowedSources: ["local_evidence_paths", "prior_run_state"],
      followUpDirection: "Compare the manual hypothesis against the current top Elo candidate."
    });
    expect(guidanceState.goal.preferences).toContain("Prefer low-cost local experiments.");
    expect(guidanceState.goal.constraints).toContain("Do not use external services.");
    expect(guidanceState.plan?.allowed_sources).toEqual(["local_evidence_paths", "prior_run_state"]);
    expect(guidanceState.user_feedback?.at(-1)).toMatchObject({
      kind: "follow_up_direction",
      target_id: "goal-1",
      influence: "scheduler_boost",
      content: "Compare the manual hypothesis against the current top Elo candidate."
    });

    const preferenceCommandState = await applyRunCommand("human-loop", {
      command: "prefer hyp-1 over hyp-2 for the next tournament"
    });
    expect(preferenceCommandState.user_feedback?.at(-1)).toMatchObject({
      kind: "preference_ranking",
      target_id: "goal-1",
      influence: "scheduler_boost",
      content: "prefer hyp-1 over hyp-2 for the next tournament"
    });

    const constraintCommandState = await applyRunCommand("human-loop", {
      command: "constraint: keep all evidence local"
    });
    expect(constraintCommandState.goal.constraints).toContain("keep all evidence local");
  });

  it("persists human proximity overrides on existing edges", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    const runDir = path.join(root, "runs", "human-loop");
    await mkdir(runDir, { recursive: true });
    const baseState = runState("Human loop");
    const editableState = {
      ...baseState,
      hypotheses: [
        ...baseState.hypotheses,
        {
          ...baseState.hypotheses[0],
          id: "hyp-2",
          title: "Diverse idea"
        }
      ],
      proximity_edges: [
        {
          source: "hyp-1",
          target: "hyp-2",
          similarity: 0.86,
          method: "embedding_proximity",
          reason: "Computed as close neighbors."
        }
      ]
    };
    await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

    const overrideState = await applyProximityOverride("human-loop", {
      source: "hyp-2",
      target: "hyp-1",
      decision: "preserve",
      clusterId: "cluster-human-review",
      reason: "Different benchmark failure mode."
    });

    expect(overrideState.proximity_edges?.[0]).toMatchObject({
      source: "hyp-1",
      target: "hyp-2",
      cluster_id: "cluster-human-review",
      diversity_action: "preserve_as_diversity_candidate",
      reason: "Computed as close neighbors. Human override: Different benchmark failure mode."
    });
    expect(overrideState.proximity_edges?.[0].deduplication_action).toBeUndefined();
    expect(overrideState.user_feedback?.at(-1)).toMatchObject({
      kind: "proximity_override",
      target_id: "hyp-1:hyp-2",
      influence: "cluster_management"
    });
    expect(overrideState.hypotheses[0].proximity_notes?.at(-1)).toContain("Human proximity override");
    expect(overrideState.hypotheses[1].proximity_notes?.at(-1)).toContain("Human proximity override");
  });

  it("persists human proximity cluster overrides across matching edges", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    const runDir = path.join(root, "runs", "cluster-loop");
    await mkdir(runDir, { recursive: true });
    const baseState = runState("Cluster loop");
    const editableState = {
      ...baseState,
      hypotheses: [
        ...baseState.hypotheses,
        { ...baseState.hypotheses[0], id: "hyp-2", title: "Second idea" },
        { ...baseState.hypotheses[0], id: "hyp-3", title: "Third idea" }
      ],
      proximity_edges: [
        {
          source: "hyp-1",
          target: "hyp-2",
          similarity: 0.9,
          method: "embedding_proximity",
          cluster_id: "cluster-repair"
        },
        {
          source: "hyp-2",
          target: "hyp-3",
          similarity: 0.82,
          method: "embedding_proximity",
          cluster_id: "cluster-repair"
        },
        {
          source: "hyp-1",
          target: "hyp-3",
          similarity: 0.2,
          method: "embedding_proximity",
          cluster_id: "cluster-ui"
        }
      ]
    };
    await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

    const overrideState = await applyProximityClusterOverride("cluster-loop", {
      clusterId: "cluster-repair",
      decision: "merge",
      reason: "Same repair-loop mechanism."
    });

    const repairEdges = overrideState.proximity_edges?.filter((edge) => edge.cluster_id === "cluster-repair") ?? [];
    expect(repairEdges).toHaveLength(2);
    expect(repairEdges.every((edge) => edge.deduplication_action === "merge_or_contrast_before_ranking")).toBe(true);
    expect(repairEdges.every((edge) => edge.diversity_action === "avoid_redundant_parallel_exploration")).toBe(true);
    expect(overrideState.proximity_edges?.find((edge) => edge.cluster_id === "cluster-ui")?.deduplication_action).toBeUndefined();
    expect(overrideState.user_feedback?.at(-1)).toMatchObject({
      kind: "proximity_cluster_override",
      target_id: "cluster-repair",
      influence: "cluster_management"
    });
    expect(
      overrideState.hypotheses.every((hypothesis) =>
        hypothesis.proximity_notes?.at(-1)?.includes("Human proximity cluster override")
      )
    ).toBe(true);
  });

  it("assigns an existing proximity edge to a named cluster from a command", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    const runDir = path.join(root, "runs", "membership-loop");
    await mkdir(runDir, { recursive: true });
    const baseState = runState("Membership loop");
    const editableState = {
      ...baseState,
      hypotheses: [
        ...baseState.hypotheses,
        { ...baseState.hypotheses[0], id: "hyp-2", title: "Second idea" }
      ],
      proximity_edges: [
        {
          source: "hyp-1",
          target: "hyp-2",
          similarity: 0.77,
          method: "embedding_proximity",
          reason: "Computed neighborhood."
        }
      ]
    };
    await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

    const commandState = await applyRunCommand("membership-loop", {
      command: "cluster hyp-2 hyp-1 as cluster-human-review"
    });

    expect(commandState.proximity_edges?.[0]).toMatchObject({
      source: "hyp-1",
      target: "hyp-2",
      cluster_id: "cluster-human-review",
      reason: "Computed neighborhood. Human cluster assignment: cluster-human-review."
    });
    expect(commandState.proximity_edges?.[0].deduplication_action).toBeUndefined();
    expect(commandState.proximity_edges?.[0].diversity_action).toBeUndefined();
    expect(commandState.user_feedback?.at(-1)).toMatchObject({
      kind: "proximity_cluster_assignment",
      target_id: "hyp-1:hyp-2",
      influence: "cluster_management"
    });
    expect(commandState.hypotheses[0].proximity_notes?.at(-1)).toContain("Human proximity cluster assignment");
    expect(commandState.hypotheses[1].proximity_notes?.at(-1)).toContain("Human proximity cluster assignment");
  });

  it("assigns existing proximity edges among multiple members to a named cluster from a command", async ({ task }) => {
    const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
    tempRoot = root;
    process.env.CODE_SCIENTIST_ROOT = root;
    const runDir = path.join(root, "runs", "multi-membership-loop");
    await mkdir(runDir, { recursive: true });
    const baseState = runState("Multi membership loop");
    const editableState = {
      ...baseState,
      hypotheses: [
        ...baseState.hypotheses,
        { ...baseState.hypotheses[0], id: "hyp-2", title: "Second idea" },
        { ...baseState.hypotheses[0], id: "hyp-3", title: "Third idea" },
        { ...baseState.hypotheses[0], id: "hyp-4", title: "Fourth idea" }
      ],
      proximity_edges: [
        {
          source: "hyp-1",
          target: "hyp-2",
          similarity: 0.77,
          method: "embedding_proximity",
          reason: "Computed 1-2 neighborhood."
        },
        {
          source: "hyp-2",
          target: "hyp-3",
          similarity: 0.71,
          method: "embedding_proximity",
          reason: "Computed 2-3 neighborhood."
        },
        {
          source: "hyp-1",
          target: "hyp-3",
          similarity: 0.69,
          method: "embedding_proximity",
          reason: "Computed 1-3 neighborhood."
        },
        {
          source: "hyp-1",
          target: "hyp-4",
          similarity: 0.41,
          method: "embedding_proximity",
          cluster_id: "cluster-ui",
          reason: "Different UI cluster."
        }
      ]
    };
    await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

    const commandState = await applyRunCommand("multi-membership-loop", {
      command: "cluster hyp-3 hyp-1 hyp-2 as cluster-human-review"
    });

    const memberPairs = new Set(["hyp-1:hyp-2", "hyp-1:hyp-3", "hyp-2:hyp-3"]);
    const memberEdges = commandState.proximity_edges?.filter((edge) =>
      memberPairs.has([edge.source, edge.target].sort().join(":"))
    );
    expect(memberEdges).toHaveLength(3);
    expect(memberEdges?.every((edge) => edge.cluster_id === "cluster-human-review")).toBe(true);
    expect(memberEdges?.every((edge) => edge.reason?.includes("Human cluster assignment"))).toBe(true);
    expect(
      commandState.proximity_edges?.find((edge) => [edge.source, edge.target].sort().join(":") === "hyp-1:hyp-4")
        ?.cluster_id
    ).toBe("cluster-ui");
    expect(commandState.user_feedback?.at(-1)).toMatchObject({
      kind: "proximity_cluster_assignment",
      target_id: "hyp-1:hyp-2:hyp-3",
      influence: "cluster_management"
    });
    expect(
      commandState.hypotheses
        .filter((hypothesis) => ["hyp-1", "hyp-2", "hyp-3"].includes(hypothesis.id))
        .every((hypothesis) => hypothesis.proximity_notes?.at(-1)?.includes("moved 3 edges"))
    ).toBe(true);
  });
});

function runState(objective: string) {
  return {
    goal: {
      id: "goal-1",
      objective,
      domain: "ai_llm_code",
      preferences: [],
      constraints: [],
      metrics: ["pass_rate"],
      safety_notes: []
    },
    run_status: "running",
    plan: {
      id: "plan-1",
      goal_id: "goal-1",
      proposal_preferences: [],
      evaluation_criteria: [],
      generation_methods: [],
      review_types: [],
      evolution_strategies: [],
      scheduler_weights: {},
      constraints: [],
      output_formats: [],
      allowed_sources: ["seed_paper_evidence"],
      allowed_tools: [],
      termination_criteria: []
    },
    evidence: [],
    hypotheses: [
      {
        id: "hyp-1",
        title: "Ranked idea",
        claim: "A claim",
        rationale: "A rationale",
        assumptions: [],
        evidence_refs: [],
        test_plan: {
          experiment: "Run an experiment",
          metrics: ["pass_rate"],
          success_condition: "Improve pass rate"
        },
        risks: [],
        origin: "generation",
        parent_ids: [],
        elo: 1200,
        status: "accepted"
      }
    ],
    reviews: [
      {
        id: "rev-1",
        hypothesis_id: "hyp-1",
        decision: "accept",
        scores: {},
        strengths: [],
        weaknesses: [],
        safety_notes: []
      }
    ],
    matches: [
      {
        id: "match-1",
        hypothesis_a: "hyp-1",
        hypothesis_b: "hyp-2",
        winner: "hyp-1",
        rationale: "Better",
        elo_before: {},
        elo_after: {}
      }
    ],
    meta_reviews: [],
    safety: { allowed: true, reason: "Allowed", flags: [] }
  };
}
