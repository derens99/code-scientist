import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Hypothesis } from "@/lib/types";
import { HumanInputPanel } from "./HumanInputPanel";

describe("HumanInputPanel", () => {
  it("renders controls for feedback, manual hypotheses, manual reviews, and verification marks", () => {
    const hypothesis: Hypothesis = {
      id: "hyp-1",
      title: "Maintainer replay memory",
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
      origin: "human",
      parent_ids: [],
      elo: 1200,
      status: "candidate"
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(HumanInputPanel, {
          selectedHypothesis: hypothesis,
          submitting: false,
          goalPreferences: [],
          goalConstraints: [],
          allowedSources: ["seed_paper_evidence"],
          onFeedback: async () => {},
          onManualHypothesis: async () => {},
          onManualReview: async () => {},
          onVerificationMark: async () => {},
          onGuidance: async () => {},
          onCommand: async () => {}
        })
      )
    );

    expect(markup).toContain("Add feedback");
    expect(markup).toContain("Mark for verification");
    expect(markup).toContain("Add hypothesis");
    expect(markup).toContain("Add review");
    expect(markup).toContain("Update guidance");
    expect(markup).toContain("Run command");
  });
});
