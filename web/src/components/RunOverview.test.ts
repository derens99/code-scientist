import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { RunState } from "@/lib/types";
import { RunOverview } from "./RunOverview";

describe("RunOverview", () => {
  it("renders live task queue status counts", () => {
    const state: RunState = {
      goal: {
        id: "goal-1",
        objective: "Find testable ideas to improve LLM coding agents",
        domain: "ai_llm_code",
        preferences: [],
        constraints: [],
        metrics: ["pass_rate"],
        safety_notes: []
      },
      run_status: "running",
      evidence: [],
      hypotheses: [],
      reviews: [],
      matches: [],
      meta_reviews: [],
      safety: { allowed: true, reason: "Allowed for local research.", flags: [] },
      task_queue: [
        task("task-1", "generate", "queued"),
        task("task-2", "review", "running"),
        task("task-3", "ranking", "completed"),
        task("task-4", "meta_review", "failed"),
        task("task-5", "overview", "deferred")
      ]
    };

    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunOverview, { summary: null, state })
      )
    );

    expect(markup).toContain("Tasks");
    expect(markup).toContain("queued=1");
    expect(markup).toContain("running=1");
    expect(markup).toContain("completed=1");
    expect(markup).toContain("failed=1");
    expect(markup).toContain("deferred=1");
  });
});

function task(id: string, kind: string, status: string) {
  return {
    id,
    kind,
    priority: 1,
    payload: { cycle: 1 },
    status,
    attempts: status === "queued" ? 0 : 1,
    result_refs: [],
    error: status === "failed" ? "provider error" : ""
  };
}
