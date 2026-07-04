import type { RunState, RunSummary } from "./types";

export type StartRunPayload = {
  objective: string;
  cycles: number;
  maxHypotheses: number;
  maxMatches: number;
  runName: string;
  provider: "deterministic" | "anthropic";
  continuous: boolean;
  intervalSeconds: number;
  maxWallMinutes: number;
  goalBriefPaths: string[];
  safetyPolicyPaths: string[];
  evidencePaths: string[];
  evidenceIndexPaths: string[];
  repoSearchPaths: string[];
  webEvidenceUrls: string[];
  webCrawlDepth: number;
  webSearchQueries: string[];
  webSearchFetch: boolean;
  webSearchCrawlDepth: number;
  literatureSearchQueries: string[];
  literatureFullText: boolean;
  capabilityEvaluationPaths: string[];
  preferenceReviewPaths: string[];
  prospectiveEvaluationPaths: string[];
  feedbackLoopEvaluationPaths: string[];
  feedbackLoopReviewPaths: string[];
};

export type UserFeedbackPayload = {
  targetId: string;
  kind: string;
  content: string;
  influence: string;
};

export type ManualHypothesisPayload = {
  title: string;
  claim: string;
  rationale: string;
  assumptions: string[];
  evidenceRefs: string[];
  experiment: string;
  metrics: string[];
  successCondition: string;
  risks: string[];
};

export type ManualReviewPayload = {
  hypothesisId: string;
  decision: "accept" | "revise" | "reject";
  strengths: string[];
  weaknesses: string[];
  safetyNotes: string[];
  findings: string[];
  evidenceRefs: string[];
  confidence: number;
  requiresRevision: boolean;
};

export type RunGuidancePayload = {
  preferences: string[];
  constraints: string[];
  allowedSources: string[];
  followUpDirection: string;
};

export type RunCommandPayload = {
  command: string;
};

export type EvaluationReturnPayload = {
  capabilityEvaluationPaths: string[];
  capabilityReviewPaths: string[];
  preferenceReviewPaths: string[];
  prospectiveEvaluationPaths: string[];
  feedbackLoopEvaluationPaths: string[];
  feedbackLoopReviewPaths: string[];
};

export type SourceAttachmentPayload = {
  evidencePaths: string[];
  evidenceIndexPaths: string[];
};

export type ProximityOverridePayload = {
  source: string;
  target: string;
  decision: "merge" | "preserve";
  clusterId?: string;
  reason?: string;
};

export type ProximityClusterOverridePayload = {
  clusterId: string;
  decision: "merge" | "preserve";
  reason?: string;
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

export async function controlRun(runId: string, action: "pause" | "resume" | "stop") {
  return parseJson<{ ok: true }>(
    await fetch(`/api/runs/${encodeURIComponent(runId)}/control`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action })
    })
  );
}

export async function submitUserFeedback(runId: string, payload: UserFeedbackPayload) {
  return postRunInput(runId, "feedback", payload);
}

export async function submitManualHypothesis(runId: string, payload: ManualHypothesisPayload) {
  return postRunInput(runId, "hypotheses", payload);
}

export async function submitManualReview(runId: string, payload: ManualReviewPayload) {
  return postRunInput(runId, "reviews", payload);
}

export async function submitRunGuidance(runId: string, payload: RunGuidancePayload) {
  return postRunInput(runId, "guidance", payload);
}

export async function submitRunCommand(runId: string, payload: RunCommandPayload) {
  return postRunInput(runId, "command", payload);
}

export async function submitEvaluationReturn(runId: string, payload: EvaluationReturnPayload) {
  return postRunInput(runId, "evaluation-return", payload);
}

export async function submitSourceAttachment(runId: string, payload: SourceAttachmentPayload) {
  return postRunInput(runId, "source-attachment", payload);
}

export async function submitProximityOverride(runId: string, payload: ProximityOverridePayload) {
  return postRunInput(runId, "proximity", payload);
}

export async function submitProximityClusterOverride(runId: string, payload: ProximityClusterOverridePayload) {
  return postRunInput(runId, "proximity-cluster", payload);
}

async function postRunInput(runId: string, segment: string, payload: unknown) {
  return parseJson<{ state: RunState }>(
    await fetch(`/api/runs/${encodeURIComponent(runId)}/${segment}`, {
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
