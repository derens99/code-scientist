import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Hypothesis, Review } from "@/lib/types";
import { HypothesisDetail } from "./HypothesisDetail";

describe("HypothesisDetail", () => {
  it("renders grounded review findings and evidence references", () => {
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
      parent_ids: ["hyp-parent"],
      generation_trace: [
        "Turn 1 objective framing: Improve LLM coding agents",
        "Turn 2 evidence scan: ev-1",
        "Generation assessment: evidence refs=1; assumptions=0."
      ],
      evolution_trace: [
        "Turn 1 query (parent mechanisms): critic before edit",
        "Turn 1 evidence: ev-mechanism",
        "Evolution assessment: strategy=evidence_grounding; retrieved evidence=1."
      ],
      elo: 1200,
      status: "merged_duplicate",
      merged_into: "hyp-keeper",
      proximity_notes: ["Deduplicated into hyp-keeper via embedding_proximity edge."]
    };
    const review: Review = {
      id: "rev-1",
      hypothesis_id: "hyp-1",
      decision: "revise",
      scores: { plausibility: 2 },
      strengths: [],
      weaknesses: ["contradicted by local evidence"],
      safety_notes: [],
      review_type: "full_review",
      evidence_refs: ["ev-1"],
      findings: ["Evidence ev-1 contradicts the hypothesis."],
      review_trace: [
        "Turn 1 query (claim mechanism): critic before edit mechanism evidence",
        "Turn 1 evidence: ev-1",
        "Assessment: benchmark evidence missing; revision required: true."
      ],
      confidence: 0.8,
      requires_revision: true
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(HypothesisDetail, { hypothesis, review, parents: [] })
      )
    );

    expect(markup).toContain("Grounded findings");
    expect(markup).toContain("Evidence ev-1 contradicts the hypothesis.");
    expect(markup).toContain("Review trace");
    expect(markup).toContain("Turn 1 query (claim mechanism)");
    expect(markup).toContain("Generation trace");
    expect(markup).toContain("Turn 1 objective framing");
    expect(markup).toContain("Evolution trace");
    expect(markup).toContain("Turn 1 query (parent mechanisms)");
    expect(markup).toContain("Merged into");
    expect(markup).toContain("hyp-keeper");
    expect(markup).toContain("Proximity decisions");
    expect(markup).toContain("Deduplicated into hyp-keeper");
    expect(markup).toContain("Evidence refs");
  });
});
