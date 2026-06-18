import { spawn } from "node:child_process";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { RunState, RunSummary } from "./types";

export type StartRunInput = {
  objective: string;
  cycles: number;
  maxHypotheses: number;
  maxMatches: number;
  runName: string;
};

export function repoRoot() {
  return process.env.CODE_SCIENTIST_ROOT
    ? path.resolve(process.env.CODE_SCIENTIST_ROOT)
    : path.resolve(process.cwd(), "..");
}

export function runsRoot() {
  return path.join(repoRoot(), "runs");
}

export function sanitizeRunName(value: string) {
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/[/\\]+/g, " ")
    .replace(/^\.+/, "")
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return cleaned || `ui-run-${Date.now()}`;
}

export function clampInteger(value: unknown, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

export async function listRuns(): Promise<RunSummary[]> {
  let entries: string[];
  try {
    entries = await readdir(runsRoot());
  } catch {
    return [];
  }

  const summaries = await Promise.all(entries.map(readRunSummary));
  return summaries
    .filter((summary): summary is RunSummary => summary !== null)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

export async function readRunState(runId: string): Promise<RunState> {
  assertSafeRunId(runId);
  return JSON.parse(await readFile(path.join(runsRoot(), runId, "state.json"), "utf8")) as RunState;
}

export async function readRunReport(runId: string) {
  assertSafeRunId(runId);
  return readFile(path.join(runsRoot(), runId, "report.md"), "utf8");
}

export async function startRun(input: StartRunInput): Promise<RunSummary> {
  const objective = input.objective.trim();
  if (!objective) {
    throw new Error("Objective is required.");
  }

  const runName = sanitizeRunName(input.runName);
  await runUv([
    "run",
    "code-scientist",
    "run",
    objective,
    "--cycles",
    String(input.cycles),
    "--max-hypotheses",
    String(input.maxHypotheses),
    "--max-matches",
    String(input.maxMatches),
    "--out",
    path.join("runs", runName)
  ]);

  const summary = await readRunSummary(runName);
  if (!summary || !summary.readable) {
    throw new Error("Run finished but no readable summary was found.");
  }
  return summary;
}

function assertSafeRunId(runId: string) {
  if (sanitizeRunName(runId) !== runId) {
    throw new Error("Invalid run id.");
  }
}

async function readRunSummary(runId: string): Promise<RunSummary | null> {
  if (sanitizeRunName(runId) !== runId) {
    return null;
  }

  const runDir = path.join(runsRoot(), runId);
  const statePath = path.join(runDir, "state.json");
  const reportPath = path.join(runDir, "report.md");

  try {
    const state = JSON.parse(await readFile(statePath, "utf8")) as RunState;
    const stateStats = await stat(statePath);
    const reportExists = await exists(reportPath);
    return {
      id: runId,
      objective: state.goal.objective,
      statePath,
      reportPath: reportExists ? reportPath : null,
      updatedAt: stateStats.mtime.toISOString(),
      hypothesisCount: state.hypotheses.length,
      reviewCount: state.reviews.length,
      matchCount: state.matches.length,
      safetyAllowed: state.safety?.allowed ?? null,
      readable: true
    };
  } catch (error) {
    return {
      id: runId,
      objective: "Unreadable run state",
      statePath,
      reportPath: null,
      updatedAt: new Date(0).toISOString(),
      hypothesisCount: 0,
      reviewCount: 0,
      matchCount: 0,
      safetyAllowed: null,
      readable: false,
      error: error instanceof Error ? error.message : "Unable to read run"
    };
  }
}

async function exists(filePath: string) {
  try {
    await stat(filePath);
    return true;
  } catch {
    return false;
  }
}

function runUv(args: string[]) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn("uv", args, {
      cwd: repoRoot(),
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(stderr.trim() || `uv exited with code ${code}`));
    });
  });
}
