import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EvaluationReturnPanel } from "./EvaluationReturnPanel";

describe("EvaluationReturnPanel", () => {
  it("renders controls for returned study packets", () => {
    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(EvaluationReturnPanel, {
          submitting: false,
          capabilityEvaluations: [],
          prospectiveEvaluations: [],
          feedbackLoopEvaluations: [],
          onEvaluationReturn: async () => {}
        })
      )
    );

    expect(markup).toContain("Returned evaluation packets");
    expect(markup).toContain("Capability reviews");
    expect(markup).toContain("Preference reviews");
    expect(markup).toContain("Prospective validations");
    expect(markup).toContain("Feedback-loop reviews");
    expect(markup).toContain("Attach returns");
  });

  it("renders inventory for attached returned evaluations", () => {
    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(EvaluationReturnPanel, {
          submitting: false,
          capabilityEvaluations: [
            {
              id: "eval-1",
              baseline_name: "single_shot_llm",
              baseline_score: 0.45,
              code_scientist_score: 0.72,
              beats_baseline: true,
              top_hypothesis_id: "hyp-1",
              elo_human_correlation: 0.91,
              elo_benchmark_correlation: 0.88,
              candidate_count: 4,
              summary: "Code Scientist beats baseline."
            }
          ],
          prospectiveEvaluations: [
            {
              id: "prospect-1",
              hypothesis_id: "hyp-1",
              status: "measured",
              implementation_refs: ["branch/candidate"],
              baseline_metrics: { pass_rate: 0.5 },
              measured_metrics: { pass_rate: 0.7 },
              deltas: { pass_rate: 0.2 },
              success: true,
              measurement_source: "held_out_repair_suite",
              measurement_status: "measured",
              notes: []
            }
          ],
          feedbackLoopEvaluations: [
            {
              id: "feedback-loop-1",
              cycle: 2,
              source_meta_review_id: "meta-1",
              feedback_agents: ["generation"],
              feedback_item_count: 3,
              adopted_feedback_count: 2,
              adoption_rate: 0.667,
              baseline_quality: { accepted_total: 2 },
              observed_quality: { accepted_total: 4 },
              deltas: { accepted_total: 2 },
              artifact_refs: ["trace-1"],
              summary: "Blind feedback-loop review improved.",
              measurement_source: "maintainer_blind_review",
              measurement_status: "measured"
            }
          ],
          onEvaluationReturn: async () => {}
        })
      )
    );

    expect(markup).toContain("Return inventory");
    expect(markup).toContain("1 capability");
    expect(markup).toContain("1 prospective");
    expect(markup).toContain("1 feedback-loop");
    expect(markup).toContain("single_shot_llm");
    expect(markup).toContain("measured via held_out_repair_suite");
    expect(markup).toContain("maintainer_blind_review");
  });
});
