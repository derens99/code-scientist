import type { RunState, RunSummary } from "./types";

export type StartRunPayload = {
  objective: string;
  cycles: number;
  maxHypotheses: number;
  maxMatches: number;
  runName: string;
};

export async function fetchRuns() {
  return parseJson<{ runs: RunSummary[] }>(await fetch("/api/runs", { cache: "no-store" }));
}

export async function fetchRunState(runId: string) {
  return parseJson<{ state: RunState }>(
    await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" })
  );
}

export async function fetchRunReport(runId: string) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/report`, { cache: "no-store" });
  if (!response.ok) {
    return "";
  }
  return response.text();
}

export async function startRun(payload: StartRunPayload) {
  return parseJson<{ run: RunSummary }>(
    await fetch("/api/runs/start", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    })
  );
}

async function parseJson<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error ?? "Request failed");
  }
  return payload as T;
}
