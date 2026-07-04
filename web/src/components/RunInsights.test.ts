import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type {
  AgentTrace,
  CapabilityEvaluation,
  Hypothesis,
  Match,
  MetaReview,
  ProximityEdge,
  ProspectiveEvaluation,
  ResearchOverview,
  SafetyEvaluationResult,
  ScalingCurvePoint,
  Task,
  UserFeedback
} from "@/lib/types";
import { RunInsights } from "./RunInsights";

describe("RunInsights", () => {
  it("renders debate match metadata", () => {
    const hypothesis: Hypothesis = {
      id: "hyp-1",
      title: "Critic-before-edit assumption decomposition",
      claim: "A claim",
      rationale: "A rationale",
      assumptions: [],
      evidence_refs: [],
      test_plan: {
        experiment: "Run a benchmark",
        metrics: ["pass_rate"],
        success_condition: "Improve pass rate"
      },
      risks: [],
      origin: "generation",
      parent_ids: [],
      elo: 1216,
      status: "accepted"
    };
    const overview: ResearchOverview = {
      id: "overview-1",
      summary: "Top candidates emphasize traceable critic loops.",
      top_hypothesis_ids: ["hyp-1"],
      promising_directions: ["critic loops"],
      next_experiments: ["Run seeded repair tasks."],
      limitations: ["Elo is not ground truth."],
      generated_by: "meta_review"
    };
    const trace: AgentTrace = {
      id: "trace-1",
      cycle: 1,
      agent: "generation",
      action: "generate",
      input_refs: ["goal-1"],
      output_refs: ["hyp-1"],
      status: "completed",
      notes: "Generated one candidate.",
      evidence_refs: []
    };
    const match: Match = {
      id: "match-1",
      hypothesis_a: "hyp-1",
      hypothesis_b: "hyp-2",
      winner: "hyp-1",
      rationale: "Heuristic comparison favored testability.",
      elo_before: { "hyp-1": 1200, "hyp-2": 1200 },
      elo_after: { "hyp-1": 1216, "hyp-2": 1184 },
      comparison_mode: "heuristic_pairwise",
      judge_trace: "debate_score hyp-1=8 hyp-2=6; manual_review hyp-1=0.75 hyp-2=0.00; winner=hyp-1",
      uncertainty: 0.25,
      review_refs: ["rev-1", "rev-2"],
      evidence_refs: ["ev-1"],
      debate_transcript: ["Pro hyp-1: stronger evidence.", "Pro hyp-2: lower cost."],
      outcome: "win"
    };
    const feedback: UserFeedback = {
      id: "feedback-1",
      kind: "preference_ranking",
      target_id: "goal-1",
      influence: "scheduler_boost",
      content: "Prefer hyp-1 over hyp-2 for the next tournament."
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [match],
          metaReviews: [],
          hypotheses: [hypothesis],
          researchOverview: overview,
          agentTraces: [trace],
          userFeedback: [feedback],
          defaultTab: "matches",
          report: ""
        })
      )
    );

    expect(markup).toContain("Matches");
    expect(markup).toContain("Debate transcript");
    expect(markup).toContain("Pro hyp-1: stronger evidence.");
    expect(markup).toContain("Evidence: ev-1");
    expect(markup).toContain("Human influence");
    expect(markup).toContain("manual_review");
    expect(markup).toContain("Prefer hyp-1 over hyp-2");
  });

  it("renders scheduler task decisions in the plan context", () => {
    const task: Task = {
      id: "task-ranking",
      kind: "ranking",
      priority: 4,
      payload: { cycle: 1, hypothesis_id: "hyp-1" },
      status: "completed",
      attempts: 1,
      result_refs: ["match-1"],
      error: "",
      worker_state: {
        scheduler_decision: {
          rank: 1,
          score: 4,
          candidate_count: 2,
          pool_size: 2,
          cycle: 1,
          signals: ["weight:ranking", "user_feedback:feedback-1"]
        }
      }
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights as React.ComponentType<any>, {
          matches: [],
          metaReviews: [],
          hypotheses: [],
          taskQueue: [task],
          defaultTab: "plan",
          report: ""
        })
      )
    );

    expect(markup).toContain("Scheduler decisions");
    expect(markup).toContain("ranking");
    expect(markup).toContain("rank 1");
    expect(markup).toContain("weight:ranking");
    expect(markup).toContain("user_feedback:feedback-1");
  });

  it("renders capability, prospective, scaling, and safety evaluations", () => {
    const hypothesis: Hypothesis = {
      id: "hyp-1",
      title: "Critic-before-edit assumption decomposition",
      claim: "A claim",
      rationale: "A rationale",
      assumptions: [],
      evidence_refs: [],
      test_plan: {
        experiment: "Run a benchmark",
        metrics: ["pass_rate"],
        success_condition: "Improve pass rate"
      },
      risks: [],
      origin: "generation",
      parent_ids: [],
      elo: 1216,
      status: "accepted"
    };
    const capability: CapabilityEvaluation = {
      id: "eval-1",
      baseline_name: "single_shot_llm",
      baseline_score: 0.45,
      code_scientist_score: 0.72,
      beats_baseline: true,
      top_hypothesis_id: "hyp-1",
      elo_human_correlation: 0.91,
      elo_benchmark_correlation: 0.88,
      candidate_count: 4,
      summary: "Code Scientist beats baseline.",
      human_preference_judgment_count: 3,
      human_preference_win_rate: 0.667
    };
    const weakerCapability: CapabilityEvaluation = {
      id: "eval-2",
      baseline_name: "baseline_reviewer",
      baseline_score: 0.6,
      code_scientist_score: 0.52,
      beats_baseline: false,
      top_hypothesis_id: "hyp-1",
      elo_human_correlation: 0.4,
      elo_benchmark_correlation: 0.2,
      candidate_count: 4,
      summary: "Code Scientist trails baseline."
    };
    const prospective: ProspectiveEvaluation = {
      id: "prospect-1",
      hypothesis_id: "hyp-1",
      status: "measured",
      implementation_refs: ["branch/candidate-workflow"],
      baseline_metrics: { pass_rate: 0.5 },
      measured_metrics: { pass_rate: 0.7 },
      deltas: { pass_rate: 0.2 },
      success: true,
      measurement_source: "held_out_repair_suite",
      measurement_status: "measured",
      notes: []
    };
    const weakerProspective: ProspectiveEvaluation = {
      id: "prospect-2",
      hypothesis_id: "hyp-2",
      status: "measured",
      implementation_refs: ["branch/weaker-workflow"],
      baseline_metrics: { pass_rate: 0.5 },
      measured_metrics: { pass_rate: 0.47 },
      deltas: { pass_rate: -0.03 },
      success: false,
      measurement_source: "proxy",
      measurement_status: "measured",
      notes: []
    };
    const scaling: ScalingCurvePoint = {
      id: "scale-1",
      label: "cycles-2-tools-20",
      cycles: 2,
      task_count: 18,
      tool_budget: 20,
      baseline_score: 0.45,
      code_scientist_score: 0.61,
      delta: 0.16,
      notes: []
    };
    const laterScaling: ScalingCurvePoint = {
      id: "scale-2",
      label: "cycles-3-tools-30",
      cycles: 3,
      task_count: 27,
      tool_budget: 30,
      baseline_score: 0.45,
      code_scientist_score: 0.65,
      delta: 0.2,
      notes: []
    };
    const safety: SafetyEvaluationResult = {
      id: "safety-1",
      suite_name: "coding_agent_safety_red_team",
      case_count: 4,
      passed_count: 4,
      failed_count: 0,
      pass_rate: 1,
      failed_case_ids: [],
      notes: []
    };
    const feedbackLoop = {
      id: "feedback-loop-1",
      cycle: 2,
      source_meta_review_id: "meta-1",
      feedback_agents: ["generation", "overview"],
      feedback_item_count: 3,
      adopted_feedback_count: 2,
      adoption_rate: 0.667,
      baseline_quality: { accepted_total: 2 },
      observed_quality: { accepted_total: 4 },
      deltas: { accepted_total: 2 },
      artifact_refs: ["trace-1"],
      summary: "Targeted feedback appeared in later artifacts.",
      measurement_source: "maintainer_blind_review",
      measurement_status: "measured"
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [],
          metaReviews: [],
          hypotheses: [hypothesis],
          capabilityEvaluations: [capability, weakerCapability],
          prospectiveEvaluations: [prospective, weakerProspective],
          scalingCurve: [scaling, laterScaling],
          safetyEvaluations: [safety],
          feedbackLoopEvaluations: [feedbackLoop],
          defaultTab: "benchmarks",
          report: ""
        })
      )
    );

    expect(markup).toContain("single_shot_llm");
    expect(markup).toContain("Capability study summary");
    expect(markup).toContain("Win rate 0.500");
    expect(markup).toContain("Mean delta +0.095");
    expect(markup).toContain("95% CI");
    expect(markup).toContain("Sign-test p");
    expect(markup).toContain("Scaling trend +0.040");
    expect(markup).toContain("Prospective success 0.500");
    expect(markup).toContain("Feedback-loop positive 1.000");
    expect(markup).toContain("Feedback-loop mean delta +2.000");
    expect(markup).toContain("Human preferences 3");
    expect(markup).toContain("Code Scientist win rate 0.667");
    expect(markup).toContain("1 feedback-loop measurements");
    expect(markup).toContain("Prospective: hyp-1");
    expect(markup).toContain("branch/candidate-workflow");
    expect(markup).toContain("measured via held_out_repair_suite");
    expect(markup).toContain("Scaling: cycles-2-tools-20");
    expect(markup).toContain("Safety: coding_agent_safety_red_team");
    expect(markup).toContain("Feedback loop: meta-1");
    expect(markup).toContain("2/3 feedback items adopted");
    expect(markup).toContain("measured via maintainer_blind_review");
  });

  it("renders agent trace task links in the overview", () => {
    const hypothesis: Hypothesis = {
      id: "hyp-1",
      title: "Critic-before-edit assumption decomposition",
      claim: "A claim",
      rationale: "A rationale",
      assumptions: [],
      evidence_refs: [],
      test_plan: {
        experiment: "Run a benchmark",
        metrics: ["pass_rate"],
        success_condition: "Improve pass rate"
      },
      risks: [],
      origin: "generation",
      parent_ids: [],
      elo: 1216,
      status: "accepted"
    };
    const trace = {
      id: "trace-1",
      cycle: 1,
      agent: "generation",
      action: "paper_seeded_idea_generation",
      task_id: "task-generate-1",
      input_refs: ["goal-1"],
      output_refs: ["hyp-1"],
      status: "completed",
      notes: "Generated one candidate.",
      evidence_refs: ["ev-1"],
      tool_calls: [
        {
          tool_name: "evidence_store.context_refs",
          status: "ok",
          evidence_refs: ["ev-1"]
        }
      ]
    } as AgentTrace;

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [],
          metaReviews: [],
          hypotheses: [hypothesis],
          agentTraces: [trace],
          defaultTab: "overview",
          report: ""
        })
      )
    );

    expect(markup).toContain("Agent trace log");
    expect(markup).toContain("Task: task-generate-1");
    expect(markup).toContain("Tool calls: evidence_store.context_refs");
  });

  it("renders research output artifacts in the overview", () => {
    const artifact = {
      id: "output-publication-1",
      output_type: "publication_brief",
      title: "Publication brief: critic loops",
      summary: "Paper-style summary for critic loops.",
      sections: {
        abstract: "Critic loops reduce repeated failures.",
        limitations: "Requires benchmark validation."
      },
      related_hypothesis_ids: ["hyp-1"],
      contact_targets: ["SWE-bench benchmark maintainer"],
      evidence_refs: ["ev-1"]
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [],
          metaReviews: [],
          hypotheses: [],
          researchOutputArtifacts: [artifact],
          defaultTab: "overview",
          report: ""
        })
      )
    );

    expect(markup).toContain("Research outputs");
    expect(markup).toContain("Publication brief: critic loops");
    expect(markup).toContain("SWE-bench benchmark maintainer");
  });

  it("renders agent-specific meta-review feedback", () => {
    const meta: MetaReview = {
      id: "meta-1",
      common_weaknesses: ["missing benchmark deltas"],
      safety_concerns: [],
      missing_evidence: [],
      promising_directions: ["critic loops"],
      prompt_feedback: ["Ground every claim."],
      agent_feedback: {
        generation: ["Use retrieved repair traces."],
        ranking: ["Prefer benchmark-backed debate evidence."]
      }
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [],
          metaReviews: [meta],
          hypotheses: [],
          defaultTab: "meta",
          report: ""
        })
      )
    );

    expect(markup).toContain("Agent feedback");
    expect(markup).toContain("generation: Use retrieved repair traces.");
    expect(markup).toContain("ranking: Prefer benchmark-backed debate evidence.");
  });

  it("renders a graph-neighborhood view for proximity edges", () => {
    const base: Hypothesis = {
      id: "hyp-a",
      title: "Assumption audit",
      claim: "A claim",
      rationale: "A rationale",
      assumptions: [],
      evidence_refs: [],
      test_plan: {
        experiment: "Run a benchmark",
        metrics: ["pass_rate"],
        success_condition: "Improve pass rate"
      },
      risks: [],
      origin: "generation",
      parent_ids: [],
      elo: 1216,
      status: "accepted"
    };
    const hypotheses = [
      base,
      { ...base, id: "hyp-b", title: "Freshness gate" },
      { ...base, id: "hyp-c", title: "Trace replay memory" }
    ];
    const edges: ProximityEdge[] = [
      {
        source: "hyp-a",
        target: "hyp-b",
        similarity: 0.82,
        method: "embedding_proximity",
        cluster_id: "cluster-audit",
        deduplication_action: "merge_or_contrast_before_ranking"
      },
      {
        source: "hyp-a",
        target: "hyp-c",
        similarity: 0.64,
        method: "semantic_evidence_overlap",
        cluster_id: "cluster-replay",
        diversity_action: "preserve_as_diversity_candidate"
      }
    ];

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [],
          metaReviews: [],
          hypotheses,
          proximityEdges: edges,
          contextSnapshots: [],
          defaultTab: "plan",
          onProximityOverride: () => undefined,
          onProximityClusterAssignment: () => undefined,
          report: ""
        })
      )
    );

    expect(markup).toContain("Graph neighborhoods");
    expect(markup).toContain("Assumption audit");
    expect(markup).toContain("Degree 2");
    expect(markup).toContain("Strongest 0.820");
    expect(markup).toContain("Clusters: cluster-audit, cluster-replay");
    expect(markup).toContain("Neighbor: Freshness gate");
    expect(markup).toContain("Neighbor: Trace replay memory");
    expect(markup).toContain("Merge edge");
    expect(markup).toContain("Preserve edge");
    expect(markup).toContain("Cluster id");
    expect(markup).toContain("Assign cluster");
  });

  it("renders proximity exploration traces", () => {
    const left: Hypothesis = {
      id: "hyp-left",
      title: "Assumption audit",
      claim: "A claim",
      rationale: "A rationale",
      assumptions: [],
      evidence_refs: ["ev-shared"],
      test_plan: {
        experiment: "Run a benchmark",
        metrics: ["pass_rate"],
        success_condition: "Improve pass rate"
      },
      risks: [],
      origin: "generation",
      parent_ids: [],
      elo: 1216,
      status: "accepted"
    };
    const right: Hypothesis = {
      ...left,
      id: "hyp-right",
      title: "Freshness gate"
    };
    const edge: ProximityEdge = {
      source: "hyp-left",
      target: "hyp-right",
      similarity: 0.75,
      method: "semantic_evidence_overlap",
      reason: "Shared evidence: ev-shared",
      cluster_id: "cluster-shared",
      evidence_refs: ["ev-shared"],
      review_refs: ["rev-left", "rev-right"],
      deduplication_action: "merge_or_contrast_before_ranking",
      diversity_action: "avoid_redundant_parallel_exploration",
      exploration_trace: [
        "Turn 1 lexical/semantic overlap: shared terms agent, memory",
        "Turn 2 evidence overlap: ev-shared",
        "Turn 3 review context: rev-left, rev-right",
        "Assessment: semantic similarity 0.75."
      ]
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunInsights, {
          matches: [],
          metaReviews: [],
          hypotheses: [left, right],
          proximityEdges: [edge],
          contextSnapshots: [],
          defaultTab: "plan",
          onProximityOverride: () => undefined,
          onProximityClusterOverride: () => undefined,
          report: ""
        })
      )
    );

    expect(markup).toContain("Proximity trace");
    expect(markup).toContain("Turn 2 evidence overlap: ev-shared");
    expect(markup).toContain("Deduplication: merge_or_contrast_before_ranking");
    expect(markup).toContain("Diversity: avoid_redundant_parallel_exploration");
    expect(markup).toContain("Merge");
    expect(markup).toContain("Preserve");
    expect(markup).toContain("Cluster overview");
    expect(markup).toContain("cluster-shared");
    expect(markup).toContain("1 edge");
    expect(markup).toContain("2 hypotheses");
    expect(markup).toContain("Merge cluster");
    expect(markup).toContain("Preserve cluster");
  });
});
