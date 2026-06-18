import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { clampInteger, listRuns, sanitizeRunName } from "./codeScientist";

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
      hypothesisCount: 1,
      reviewCount: 1,
      matchCount: 1,
      safetyAllowed: true,
      readable: true
    });
    expect(runs[0].reportPath).toContain("report.md");
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
