import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import type { RunState, RunSummary } from "./types";

export type StartRunInput = {
  objective: string;
  cycles: number;
  maxHypotheses: number;
  maxMatches: number;
  runName: string;
  provider?: "deterministic" | "anthropic";
  continuous?: boolean;
  intervalSeconds?: number;
  maxWallMinutes?: number;
  goalBriefPaths?: string[];
  safetyPolicyPaths?: string[];
  evidencePaths?: string[];
  evidenceIndexPaths?: string[];
  repoSearchPaths?: string[];
  webEvidenceUrls?: string[];
  webCrawlDepth?: number;
  webSearchQueries?: string[];
  webSearchFetch?: boolean;
  webSearchCrawlDepth?: number;
  literatureSearchQueries?: string[];
  literatureFullText?: boolean;
  capabilityEvaluationPaths?: string[];
  preferenceReviewPaths?: string[];
  prospectiveEvaluationPaths?: string[];
  feedbackLoopEvaluationPaths?: string[];
  feedbackLoopReviewPaths?: string[];
  agentRetrieval?: boolean;
  toolBudget?: number;
  agentValidationManifestPaths?: string[];
  agentRetrievalIterations?: number;
  agentFetchDomains?: string[];
  reviewProcesses?: number;
  providerCallBudget?: number;
  pdfVision?: boolean;
  pdfVisionMaxRegions?: number;
  pdfVisionCallBudget?: number;
};

export type UserFeedbackInput = {
  targetId: string;
  kind: string;
  content: string;
  influence?: string;
};

export type ManualHypothesisInput = {
  title: string;
  claim: string;
  rationale: string;
  assumptions?: string[];
  evidenceRefs?: string[];
  experiment: string;
  metrics?: string[];
  successCondition: string;
  risks?: string[];
};

export type ManualReviewInput = {
  hypothesisId: string;
  decision: string;
  strengths?: string[];
  weaknesses?: string[];
  safetyNotes?: string[];
  findings?: string[];
  evidenceRefs?: string[];
  confidence?: number;
  requiresRevision?: boolean;
};

export type RunGuidanceInput = {
  objective?: string;
  preferences?: string[];
  constraints?: string[];
  metrics?: string[];
  safetyNotes?: string[];
  allowedSources?: string[];
  allowedTools?: string[];
  outputFormats?: string[];
  terminationCriteria?: string[];
  followUpDirection?: string;
};

export type RunCommandInput = {
  command: string;
};

export type EvaluationReturnInput = {
  capabilityEvaluationPaths?: string[];
  capabilityReviewPaths?: string[];
  preferenceReviewPaths?: string[];
  prospectiveEvaluationPaths?: string[];
  feedbackLoopEvaluationPaths?: string[];
  feedbackLoopReviewPaths?: string[];
};

export type SourceAttachmentInput = {
  evidencePaths?: string[];
  evidenceIndexPaths?: string[];
};

type ClusterAssignmentCommand =
  | { kind: "edge"; source: string; target: string; clusterId: string }
  | { kind: "members"; hypothesisIds: string[]; clusterId: string };

export type ProximityOverrideInput = {
  source: string;
  target: string;
  decision: "merge" | "preserve";
  clusterId?: string;
  reason?: string;
};

export type ProximityClusterOverrideInput = {
  clusterId: string;
  decision: "merge" | "preserve";
  reason?: string;
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

export async function appendUserFeedback(runId: string, input: UserFeedbackInput): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const targetId = requiredText(input.targetId, "Feedback target");
    const kind = requiredText(input.kind, "Feedback kind");
    const content = requiredText(input.content, "Feedback content");
    const influence = input.influence?.trim() || "informational";
    const index = state.user_feedback?.length ?? 0;
    return {
      ...state,
      user_feedback: [
        ...(state.user_feedback ?? []),
        {
          id: stableId("feedback", `${state.goal.id}:${targetId}:${kind}:${influence}:${content}:${index}`),
          kind,
          target_id: targetId,
          content,
          influence
        }
      ]
    };
  });
}

export async function appendManualHypothesis(runId: string, input: ManualHypothesisInput): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const title = requiredText(input.title, "Hypothesis title");
    const claim = requiredText(input.claim, "Hypothesis claim");
    const rationale = requiredText(input.rationale, "Hypothesis rationale");
    const experiment = requiredText(input.experiment, "Test experiment");
    const successCondition = requiredText(input.successCondition, "Success condition");
    const metrics = cleanList(input.metrics);
    const index = state.hypotheses.length;
    return {
      ...state,
      hypotheses: [
        ...state.hypotheses,
        {
          id: stableId("hyp", `${state.goal.id}:human:${title}:${claim}:${index}`),
          title,
          claim,
          rationale,
          assumptions: cleanList(input.assumptions),
          evidence_refs: cleanList(input.evidenceRefs),
          test_plan: {
            experiment,
            metrics: metrics.length ? metrics : ["human_judgment"],
            success_condition: successCondition
          },
          risks: cleanList(input.risks),
          origin: "human",
          parent_ids: [],
          elo: 1200,
          status: "candidate"
        }
      ]
    };
  });
}

export async function appendManualReview(runId: string, input: ManualReviewInput): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const hypothesisId = requiredText(input.hypothesisId, "Hypothesis");
    if (!state.hypotheses.some((hypothesis) => hypothesis.id === hypothesisId)) {
      throw new Error("Manual review target was not found.");
    }
    const decision = requiredDecision(input.decision);
    const index = state.reviews.length;
    return {
      ...state,
      reviews: [
        ...state.reviews,
        {
          id: stableId("rev", `${state.goal.id}:manual:${hypothesisId}:${decision}:${index}`),
          hypothesis_id: hypothesisId,
          decision,
          scores: {},
          strengths: cleanList(input.strengths),
          weaknesses: cleanList(input.weaknesses),
          safety_notes: cleanList(input.safetyNotes),
          review_type: "manual_review",
          evidence_refs: cleanList(input.evidenceRefs),
          findings: cleanList(input.findings),
          confidence: clampNumber(input.confidence, 0, 1, 0.5),
          requires_revision: Boolean(input.requiresRevision)
        }
      ]
    };
  });
}

export async function updateRunGuidance(runId: string, input: RunGuidanceInput): Promise<RunState> {
  assertSafeRunId(runId);
  const patch = {
    ...(input.objective?.trim() ? { objective: input.objective.trim() } : {}),
    ...(input.preferences !== undefined ? { preferences: cleanList(input.preferences) } : {}),
    ...(input.constraints !== undefined ? { constraints: cleanList(input.constraints) } : {}),
    ...(input.metrics !== undefined ? { metrics: cleanList(input.metrics) } : {}),
    ...(input.safetyNotes !== undefined ? { safety_notes: cleanList(input.safetyNotes) } : {}),
    ...(input.allowedSources !== undefined ? { allowed_sources: cleanList(input.allowedSources) } : {}),
    ...(input.allowedTools !== undefined ? { allowed_tools: cleanList(input.allowedTools) } : {}),
    ...(input.outputFormats !== undefined ? { output_formats: cleanList(input.outputFormats) } : {}),
    ...(input.terminationCriteria !== undefined
      ? { termination_criteria: cleanList(input.terminationCriteria) }
      : {}),
    ...(input.followUpDirection?.trim()
      ? { follow_up_direction: input.followUpDirection.trim() }
      : {})
  };
  await runEngineUv([
    "run",
    "code-scientist",
    "goal-revision",
    path.join(runsRoot(), runId),
    "--patch-json",
    JSON.stringify(patch),
    "--message",
    input.followUpDirection?.trim() || "Workbench goal guidance update"
  ]);
  return readRunState(runId);
}

export async function applyProximityOverride(runId: string, input: ProximityOverrideInput): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const source = requiredText(input.source, "Proximity source");
    const target = requiredText(input.target, "Proximity target");
    if (source === target) {
      throw new Error("Proximity override requires two different hypotheses.");
    }
    const knownHypotheses = new Set(state.hypotheses.map((hypothesis) => hypothesis.id));
    if (!knownHypotheses.has(source) || !knownHypotheses.has(target)) {
      throw new Error("Proximity override target was not found.");
    }

    const decision = requiredProximityDecision(input.decision);
    const pairKey = proximityPairKey(source, target);
    const clusterId = input.clusterId?.trim() || undefined;
    const reason = input.reason?.trim() || "";
    let matched = false;
    const proximityEdges = (state.proximity_edges ?? []).map((edge) => {
      if (proximityPairKey(edge.source, edge.target) !== pairKey) {
        return edge;
      }
      matched = true;
      return {
        ...edge,
        cluster_id: clusterId ?? edge.cluster_id,
        reason: appendHumanOverrideReason(edge.reason, reason),
        deduplication_action: decision === "merge" ? "merge_or_contrast_before_ranking" : undefined,
        diversity_action:
          decision === "merge"
            ? "avoid_redundant_parallel_exploration"
            : "preserve_as_diversity_candidate"
      };
    });
    if (!matched) {
      throw new Error("Proximity edge was not found.");
    }

    const note = humanProximityOverrideNote(pairKey, decision, clusterId, reason);
    const userFeedback = [...(state.user_feedback ?? [])];
    userFeedback.push({
      id: stableId("feedback", `${state.goal.id}:proximity:${pairKey}:${decision}:${reason}:${userFeedback.length}`),
      kind: "proximity_override",
      target_id: pairKey,
      content: note,
      influence: "cluster_management"
    });

    return {
      ...state,
      hypotheses: state.hypotheses.map((hypothesis) =>
        hypothesis.id === source || hypothesis.id === target
          ? {
              ...hypothesis,
              proximity_notes: mergeUnique(hypothesis.proximity_notes ?? [], [note])
            }
          : hypothesis
      ),
      proximity_edges: proximityEdges,
      user_feedback: userFeedback
    };
  });
}

export async function applyProximityClusterOverride(
  runId: string,
  input: ProximityClusterOverrideInput
): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const clusterId = requiredText(input.clusterId, "Proximity cluster");
    const decision = requiredProximityDecision(input.decision);
    const reason = input.reason?.trim() || "";
    const touchedHypotheses = new Set<string>();
    let matchedEdges = 0;
    const proximityEdges = (state.proximity_edges ?? []).map((edge) => {
      if ((edge.cluster_id ?? "unclustered") !== clusterId) {
        return edge;
      }
      matchedEdges += 1;
      touchedHypotheses.add(edge.source);
      touchedHypotheses.add(edge.target);
      return {
        ...edge,
        reason: appendHumanClusterOverrideReason(edge.reason, reason),
        deduplication_action: decision === "merge" ? "merge_or_contrast_before_ranking" : undefined,
        diversity_action:
          decision === "merge"
            ? "avoid_redundant_parallel_exploration"
            : "preserve_as_diversity_candidate"
      };
    });
    if (!matchedEdges) {
      throw new Error("Proximity cluster was not found.");
    }

    const note = humanProximityClusterOverrideNote(clusterId, decision, matchedEdges, reason);
    const userFeedback = [...(state.user_feedback ?? [])];
    userFeedback.push({
      id: stableId("feedback", `${state.goal.id}:proximity-cluster:${clusterId}:${decision}:${reason}:${userFeedback.length}`),
      kind: "proximity_cluster_override",
      target_id: clusterId,
      content: note,
      influence: "cluster_management"
    });

    return {
      ...state,
      hypotheses: state.hypotheses.map((hypothesis) =>
        touchedHypotheses.has(hypothesis.id)
          ? {
              ...hypothesis,
              proximity_notes: mergeUnique(hypothesis.proximity_notes ?? [], [note])
            }
          : hypothesis
      ),
      proximity_edges: proximityEdges,
      user_feedback: userFeedback
    };
  });
}

export async function assignProximityEdgeCluster(
  runId: string,
  input: { source: string; target: string; clusterId: string }
): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const source = requiredText(input.source, "Proximity source");
    const target = requiredText(input.target, "Proximity target");
    const clusterId = requiredText(input.clusterId, "Proximity cluster");
    if (source === target) {
      throw new Error("Proximity cluster assignment requires two different hypotheses.");
    }
    const knownHypotheses = new Set(state.hypotheses.map((hypothesis) => hypothesis.id));
    if (!knownHypotheses.has(source) || !knownHypotheses.has(target)) {
      throw new Error("Proximity cluster assignment target was not found.");
    }

    const pairKey = proximityPairKey(source, target);
    let matched = false;
    const proximityEdges = (state.proximity_edges ?? []).map((edge) => {
      if (proximityPairKey(edge.source, edge.target) !== pairKey) {
        return edge;
      }
      matched = true;
      return {
        ...edge,
        cluster_id: clusterId,
        reason: appendHumanClusterAssignmentReason(edge.reason, clusterId)
      };
    });
    if (!matched) {
      throw new Error("Proximity edge was not found.");
    }

    const note = `Human proximity cluster assignment for ${pairKey}: moved to ${clusterId}.`;
    const userFeedback = [...(state.user_feedback ?? [])];
    userFeedback.push({
      id: stableId("feedback", `${state.goal.id}:proximity-cluster-assignment:${pairKey}:${clusterId}:${userFeedback.length}`),
      kind: "proximity_cluster_assignment",
      target_id: pairKey,
      content: note,
      influence: "cluster_management"
    });

    return {
      ...state,
      hypotheses: state.hypotheses.map((hypothesis) =>
        hypothesis.id === source || hypothesis.id === target
          ? {
              ...hypothesis,
              proximity_notes: mergeUnique(hypothesis.proximity_notes ?? [], [note])
            }
          : hypothesis
      ),
      proximity_edges: proximityEdges,
      user_feedback: userFeedback
    };
  });
}

export async function assignProximityClusterMembers(
  runId: string,
  input: { hypothesisIds: string[]; clusterId: string }
): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const hypothesisIds = mergeUnique([], cleanList(input.hypothesisIds));
    const clusterId = requiredText(input.clusterId, "Proximity cluster");
    if (hypothesisIds.length < 2) {
      throw new Error("Proximity cluster assignment requires at least two hypotheses.");
    }
    const knownHypotheses = new Set(state.hypotheses.map((hypothesis) => hypothesis.id));
    if (hypothesisIds.some((hypothesisId) => !knownHypotheses.has(hypothesisId))) {
      throw new Error("Proximity cluster assignment target was not found.");
    }

    const sortedMemberIds = [...hypothesisIds].sort();
    const memberKey = sortedMemberIds.join(":");
    const memberPairs = new Set<string>();
    for (let leftIndex = 0; leftIndex < sortedMemberIds.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < sortedMemberIds.length; rightIndex += 1) {
        memberPairs.add(proximityPairKey(sortedMemberIds[leftIndex], sortedMemberIds[rightIndex]));
      }
    }

    const touchedHypotheses = new Set<string>();
    let matchedEdges = 0;
    const proximityEdges = (state.proximity_edges ?? []).map((edge) => {
      const pairKey = proximityPairKey(edge.source, edge.target);
      if (!memberPairs.has(pairKey)) {
        return edge;
      }
      matchedEdges += 1;
      touchedHypotheses.add(edge.source);
      touchedHypotheses.add(edge.target);
      return {
        ...edge,
        cluster_id: clusterId,
        reason: appendHumanClusterAssignmentReason(edge.reason, clusterId)
      };
    });
    if (!matchedEdges) {
      throw new Error("No proximity edges were found for the requested cluster members.");
    }

    const edgeLabel = matchedEdges === 1 ? "edge" : "edges";
    const note = `Human proximity cluster assignment for ${memberKey}: moved ${matchedEdges} ${edgeLabel} to ${clusterId}.`;
    const userFeedback = [...(state.user_feedback ?? [])];
    userFeedback.push({
      id: stableId("feedback", `${state.goal.id}:proximity-cluster-assignment:${memberKey}:${clusterId}:${userFeedback.length}`),
      kind: "proximity_cluster_assignment",
      target_id: memberKey,
      content: note,
      influence: "cluster_management"
    });

    return {
      ...state,
      hypotheses: state.hypotheses.map((hypothesis) =>
        touchedHypotheses.has(hypothesis.id)
          ? {
              ...hypothesis,
              proximity_notes: mergeUnique(hypothesis.proximity_notes ?? [], [note])
            }
          : hypothesis
      ),
      proximity_edges: proximityEdges,
      user_feedback: userFeedback
    };
  });
}

export async function applyRunCommand(runId: string, input: RunCommandInput): Promise<RunState> {
  const command = requiredText(input.command, "Command");
  const lower = command.toLowerCase();
  const labeled = parseLabeledCommand(command);
  if (labeled?.label === "constraint") {
    return updateRunGuidance(runId, { constraints: [labeled.value] });
  }
  if (labeled?.label === "preference") {
    return updateRunGuidance(runId, { preferences: [labeled.value] });
  }
  if (labeled?.label === "follow-up" || labeled?.label === "followup") {
    return updateRunGuidance(runId, { followUpDirection: labeled.value });
  }

  const clusterAssignment = parseClusterAssignmentCommand(command);
  if (clusterAssignment) {
    if (clusterAssignment.kind === "members") {
      return assignProximityClusterMembers(runId, clusterAssignment);
    }
    return assignProximityEdgeCluster(runId, clusterAssignment);
  }

  const verifyTarget = lower.includes("verify") ? command.match(/hyp-[a-z0-9-]+/i)?.[0] : null;
  if (verifyTarget) {
    return appendUserFeedback(runId, {
      targetId: verifyTarget,
      kind: "verification_request",
      content: command,
      influence: "scheduler_boost"
    });
  }

  if (lower.includes("prefer") && lower.includes("over")) {
    return appendGoalFeedback(runId, "preference_ranking", command, "scheduler_boost");
  }

  return appendGoalFeedback(runId, "command_note", command, "informational");
}

export async function readRunReport(runId: string) {
  assertSafeRunId(runId);
  return readFile(path.join(runsRoot(), runId, "report.md"), "utf8");
}

export function buildRunArgs(input: StartRunInput) {
  const runName = sanitizeRunName(input.runName);
  const args = [
    "run",
    "code-scientist",
    "run",
    input.objective.trim(),
    "--cycles",
    String(input.cycles),
    "--max-hypotheses",
    String(input.maxHypotheses),
    "--max-matches",
    String(input.maxMatches),
    "--provider",
    input.provider ?? "deterministic"
  ];

  if (input.continuous) {
    args.push("--continuous");
    args.push("--interval-seconds", String(input.intervalSeconds ?? 60));
    if (input.maxWallMinutes !== undefined) {
      args.push("--max-wall-minutes", String(input.maxWallMinutes));
    }
  }

  const reviewProcesses = Math.max(0, Math.trunc(Number(input.reviewProcesses ?? 0)));
  if (reviewProcesses > 0) {
    args.push("--review-processes", String(reviewProcesses));
  }
  if (input.provider === "anthropic") {
    const providerCallBudget = Math.max(
      1,
      Math.trunc(Number(input.providerCallBudget ?? 100))
    );
    args.push("--provider-call-budget", String(providerCallBudget));
    if (input.pdfVision) {
      args.push("--pdf-vision");
      args.push(
        "--pdf-vision-max-regions",
        String(Math.max(0, Math.min(100, Math.trunc(Number(input.pdfVisionMaxRegions ?? 10)))))
      );
      args.push(
        "--pdf-vision-call-budget",
        String(Math.max(1, Math.trunc(Number(input.pdfVisionCallBudget ?? 10))))
      );
    }
  }

  for (const goalBriefPath of cleanList(input.goalBriefPaths)) {
    args.push("--goal-brief", goalBriefPath);
  }

  for (const safetyPolicyPath of cleanList(input.safetyPolicyPaths)) {
    args.push("--safety-policy", safetyPolicyPath);
  }

  for (const evidencePath of cleanList(input.evidencePaths)) {
    args.push("--evidence-path", evidencePath);
  }

  for (const evidenceIndexPath of cleanList(input.evidenceIndexPaths)) {
    args.push("--evidence-index", evidenceIndexPath);
  }

  for (const repoSearchPath of cleanList(input.repoSearchPaths)) {
    args.push("--repo-search-path", repoSearchPath);
  }

  for (const webEvidenceUrl of cleanList(input.webEvidenceUrls)) {
    args.push("--web-evidence-url", webEvidenceUrl);
  }

  const webCrawlDepth = Math.max(0, Math.trunc(Number(input.webCrawlDepth ?? 0)));
  if (webCrawlDepth > 0) {
    args.push("--web-crawl-depth", String(webCrawlDepth));
  }

  for (const webSearchQuery of cleanList(input.webSearchQueries)) {
    args.push("--web-search-query", webSearchQuery);
  }

  if (input.webSearchFetch) {
    args.push("--web-search-fetch");
  }

  const webSearchCrawlDepth = Math.max(0, Math.trunc(Number(input.webSearchCrawlDepth ?? 0)));
  if (webSearchCrawlDepth > 0) {
    args.push("--web-search-crawl-depth", String(webSearchCrawlDepth));
  }

  for (const literatureSearchQuery of cleanList(input.literatureSearchQueries)) {
    args.push("--literature-search-query", literatureSearchQuery);
  }

  if (input.literatureFullText) {
    args.push("--literature-full-text");
  }

  const agentValidationManifestPaths = cleanList(input.agentValidationManifestPaths);
  if (input.agentRetrieval || agentValidationManifestPaths.length > 0) {
    args.push("--agent-retrieval");
    const retrievalIterations = Math.min(
      10,
      Math.max(1, Math.trunc(Number(input.agentRetrievalIterations ?? 2)))
    );
    args.push("--agent-retrieval-iterations", String(retrievalIterations));
    for (const domain of cleanList(input.agentFetchDomains)) {
      args.push("--agent-fetch-domain", domain);
    }
    const toolBudget = Math.max(0, Math.trunc(Number(input.toolBudget ?? 0)));
    if (toolBudget > 0) {
      args.push("--tool-budget", String(toolBudget));
    }
  }

  for (const manifestPath of agentValidationManifestPaths) {
    args.push("--agent-validation-manifest", manifestPath);
  }

  for (const capabilityEvaluationPath of cleanList(input.capabilityEvaluationPaths)) {
    args.push("--capability-eval-fixture", capabilityEvaluationPath);
  }

  for (const preferenceReviewPath of cleanList(input.preferenceReviewPaths)) {
    args.push("--preference-review-fixture", preferenceReviewPath);
  }

  for (const prospectiveEvaluationPath of cleanList(input.prospectiveEvaluationPaths)) {
    args.push("--prospective-eval-fixture", prospectiveEvaluationPath);
  }

  for (const feedbackLoopEvaluationPath of cleanList(input.feedbackLoopEvaluationPaths)) {
    args.push("--feedback-loop-eval-fixture", feedbackLoopEvaluationPath);
  }

  for (const feedbackLoopReviewPath of cleanList(input.feedbackLoopReviewPaths)) {
    args.push("--feedback-loop-review-fixture", feedbackLoopReviewPath);
  }

  args.push("--out", path.join("runs", runName));
  return args;
}

export async function startRun(input: StartRunInput): Promise<RunSummary> {
  const objective = input.objective.trim();
  if (!objective) {
    throw new Error("Objective is required.");
  }

  const runName = sanitizeRunName(input.runName);
  const args = buildRunArgs({ ...input, objective, runName });
  if (input.continuous) {
    startDetachedUv(args);
    return waitForRunSummary(runName);
  }

  await runUv(args);

  const summary = await readRunSummary(runName);
  if (!summary || !summary.readable) {
    throw new Error("Run finished but no readable summary was found.");
  }
  return summary;
}

export async function writeRunControl(runId: string, action: "pause" | "resume" | "stop") {
  assertSafeRunId(runId);
  const controlAction = action === "resume" ? "run" : action;
  const runDir = path.join(runsRoot(), runId);
  await mkdir(runDir, { recursive: true });
  await writeFile(
    path.join(runDir, "control.json"),
    JSON.stringify({ action: controlAction }, null, 2),
    "utf8"
  );
}

export function buildEvaluationReturnArgs(runId: string, input: EvaluationReturnInput) {
  assertSafeRunId(runId);
  const args = ["run", "code-scientist", "evaluation-return", path.join("runs", runId)];

  for (const capabilityEvaluationPath of cleanList(input.capabilityEvaluationPaths)) {
    args.push("--capability-eval-fixture", capabilityEvaluationPath);
  }

  for (const capabilityReviewPath of cleanList(input.capabilityReviewPaths)) {
    args.push("--capability-review-fixture", capabilityReviewPath);
  }

  for (const preferenceReviewPath of cleanList(input.preferenceReviewPaths)) {
    args.push("--preference-review-fixture", preferenceReviewPath);
  }

  for (const prospectiveEvaluationPath of cleanList(input.prospectiveEvaluationPaths)) {
    args.push("--prospective-eval-fixture", prospectiveEvaluationPath);
  }

  for (const feedbackLoopEvaluationPath of cleanList(input.feedbackLoopEvaluationPaths)) {
    args.push("--feedback-loop-eval-fixture", feedbackLoopEvaluationPath);
  }

  for (const feedbackLoopReviewPath of cleanList(input.feedbackLoopReviewPaths)) {
    args.push("--feedback-loop-review-fixture", feedbackLoopReviewPath);
  }

  return args;
}

export async function appendEvaluationReturns(runId: string, input: EvaluationReturnInput): Promise<RunState> {
  const args = buildEvaluationReturnArgs(runId, input);
  await runUv(args);
  return readRunState(runId);
}

export function buildSourceAttachmentArgs(runId: string, input: SourceAttachmentInput) {
  assertSafeRunId(runId);
  const args = ["run", "code-scientist", "source-attachment", path.join("runs", runId)];

  for (const evidencePath of cleanList(input.evidencePaths)) {
    args.push("--evidence-path", evidencePath);
  }

  for (const evidenceIndexPath of cleanList(input.evidenceIndexPaths)) {
    args.push("--evidence-index", evidenceIndexPath);
  }

  return args;
}

export async function appendSourceAttachments(runId: string, input: SourceAttachmentInput): Promise<RunState> {
  const args = buildSourceAttachmentArgs(runId, input);
  await runUv(args);
  return readRunState(runId);
}

async function updateRunState(runId: string, updater: (state: RunState) => RunState): Promise<RunState> {
  assertSafeRunId(runId);
  const statePath = path.join(runsRoot(), runId, "state.json");
  const state = await readRunState(runId);
  const updated = updater(state);
  await writeFile(statePath, JSON.stringify(updated, null, 2), "utf8");
  return updated;
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
    const latestSnapshot = state.context_snapshots?.at(-1) ?? null;
    return {
      id: runId,
      objective: state.goal.objective,
      statePath,
      reportPath: reportExists ? reportPath : null,
      updatedAt: stateStats.mtime.toISOString(),
      runStatus: state.run_status ?? "completed",
      latestCycle: latestSnapshot?.cycle ?? null,
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
      runStatus: "unreadable",
      latestCycle: null,
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

function runEngineUv(args: string[]) {
  const engineRoot = process.env.CODE_SCIENTIST_ENGINE_ROOT
    ? path.resolve(process.env.CODE_SCIENTIST_ENGINE_ROOT)
    : path.resolve(process.cwd(), "..");
  return new Promise<void>((resolve, reject) => {
    const child = spawn("uv", args, {
      cwd: engineRoot,
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
      } else {
        reject(new Error(stderr.trim() || `uv exited with code ${code}`));
      }
    });
  });
}

function startDetachedUv(args: string[]) {
  const child = spawn("uv", args, {
    cwd: repoRoot(),
    detached: true,
    stdio: "ignore"
  });
  child.unref();
}

async function waitForRunSummary(runName: string) {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const summary = await readRunSummary(runName);
    if (summary?.readable) {
      return summary;
    }
    await delay(100);
  }
  throw new Error("Continuous run started but no readable state was found.");
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stableId(prefix: string, text: string) {
  const digest = createHash("sha1").update(text).digest("hex").slice(0, 12);
  return `${prefix}-${digest}`;
}

function requiredText(value: string | undefined, label: string) {
  const cleaned = value?.trim() ?? "";
  if (!cleaned) {
    throw new Error(`${label} is required.`);
  }
  return cleaned;
}

function cleanList(values: string[] | undefined) {
  return (values ?? []).map((value) => value.trim()).filter(Boolean);
}

function mergeUnique(existing: string[], additions: string[]) {
  const values: string[] = [];
  const seen = new Set<string>();
  for (const value of [...existing, ...additions]) {
    if (!seen.has(value)) {
      seen.add(value);
      values.push(value);
    }
  }
  return values;
}

function proximityPairKey(source: string, target: string) {
  return [source, target].sort().join(":");
}

function requiredProximityDecision(value: string) {
  const decision = value.trim();
  if (decision !== "merge" && decision !== "preserve") {
    throw new Error("Proximity override decision must be merge or preserve.");
  }
  return decision;
}

function appendHumanOverrideReason(existingReason: string | undefined, overrideReason: string) {
  if (!overrideReason) {
    return existingReason;
  }
  const suffix = `Human override: ${overrideReason}`;
  if (!existingReason) {
    return suffix;
  }
  if (existingReason.includes(suffix)) {
    return existingReason;
  }
  return `${existingReason} ${suffix}`;
}

function appendHumanClusterOverrideReason(existingReason: string | undefined, overrideReason: string) {
  if (!overrideReason) {
    return existingReason;
  }
  const suffix = `Human cluster override: ${overrideReason}`;
  if (!existingReason) {
    return suffix;
  }
  if (existingReason.includes(suffix)) {
    return existingReason;
  }
  return `${existingReason} ${suffix}`;
}

function appendHumanClusterAssignmentReason(existingReason: string | undefined, clusterId: string) {
  const suffix = `Human cluster assignment: ${clusterId}.`;
  if (!existingReason) {
    return suffix;
  }
  if (existingReason.includes(suffix)) {
    return existingReason;
  }
  return `${existingReason} ${suffix}`;
}

function humanProximityOverrideNote(
  pairKey: string,
  decision: "merge" | "preserve",
  clusterId: string | undefined,
  reason: string
) {
  const action = decision === "merge" ? "merge/deduplicate" : "preserve diversity";
  const details = [action, clusterId ? `cluster ${clusterId}` : "", reason]
    .filter(Boolean)
    .join("; ");
  return `Human proximity override for ${pairKey}: ${details}.`;
}

function humanProximityClusterOverrideNote(
  clusterId: string,
  decision: "merge" | "preserve",
  edgeCount: number,
  reason: string
) {
  const action = decision === "merge" ? "merge/deduplicate cluster" : "preserve cluster diversity";
  const edgeLabel = edgeCount === 1 ? "edge" : "edges";
  const details = [action, `${edgeCount} ${edgeLabel}`, reason]
    .filter(Boolean)
    .join("; ");
  return `Human proximity cluster override for ${clusterId}: ${details}.`;
}

function parseLabeledCommand(command: string) {
  const match = command.match(/^\s*([a-z-]+)\s*:\s*(.+)$/i);
  if (!match) {
    return null;
  }
  return { label: match[1].toLowerCase(), value: match[2].trim() };
}

function parseClusterAssignmentCommand(command: string): ClusterAssignmentCommand | null {
  const match = command.match(/^\s*cluster\s+(.+?)\s+(?:as|into|to)\s+([a-z0-9._-]+)\s*$/i);
  if (!match) {
    return null;
  }
  const hypothesisIds = match[1].match(/hyp-[a-z0-9-]+/gi) ?? [];
  const uniqueHypothesisIds = mergeUnique([], hypothesisIds);
  if (uniqueHypothesisIds.length < 2) {
    return null;
  }
  if (uniqueHypothesisIds.length > 2) {
    return {
      kind: "members",
      hypothesisIds: uniqueHypothesisIds,
      clusterId: match[2]
    };
  }
  return {
    kind: "edge",
    source: uniqueHypothesisIds[0],
    target: uniqueHypothesisIds[1],
    clusterId: match[2]
  };
}

function appendGoalFeedback(
  runId: string,
  kind: string,
  content: string,
  influence: string
): Promise<RunState> {
  return updateRunState(runId, (state) => {
    const userFeedback = [...(state.user_feedback ?? [])];
    userFeedback.push({
      id: stableId("feedback", `${state.goal.id}:${kind}:${content}:${userFeedback.length}`),
      kind,
      target_id: state.goal.id,
      content,
      influence
    });
    return { ...state, user_feedback: userFeedback };
  });
}

function requiredDecision(value: string) {
  const decision = value.trim();
  if (!["accept", "revise", "reject"].includes(decision)) {
    throw new Error("Manual review decision must be accept, revise, or reject.");
  }
  return decision;
}

function clampNumber(value: number | undefined, min: number, max: number, fallback: number) {
  if (value === undefined || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, value));
}
