import { NextResponse } from "next/server";
import { clampInteger, sanitizeRunName, startRun } from "@/lib/codeScientist";
import { assertTrustedMutationRequest, mutationErrorStatus } from "@/lib/requestSecurity";

export const runtime = "nodejs";

const WORKBENCH_PROVIDERS = ["deterministic", "anthropic", "claude-cli", "codex-cli"] as const;
type WorkbenchProvider = (typeof WORKBENCH_PROVIDERS)[number];

export async function POST(request: Request) {
  try {
    assertTrustedMutationRequest(request);
    const body = await request.json();
    const requestedProvider = String(body.provider ?? "deterministic");
    if (requestedProvider === "host-agent") {
      return NextResponse.json(
        {
          error:
            "The host-agent provider needs a live agent session answering the run's llm-bridge requests; start it from Claude Code or Codex instead of the workbench."
        },
        { status: 400 }
      );
    }
    const provider: WorkbenchProvider = (WORKBENCH_PROVIDERS as readonly string[]).includes(
      requestedProvider
    )
      ? (requestedProvider as WorkbenchProvider)
      : "deterministic";
    const run = await startRun({
      objective: String(body.objective ?? ""),
      cycles: clampInteger(body.cycles, 1, 5, 1),
      maxHypotheses: clampInteger(body.maxHypotheses, 2, 20, 6),
      maxMatches: clampInteger(body.maxMatches, 0, 40, 4),
      provider,
      continuous: Boolean(body.continuous),
      intervalSeconds: clampInteger(body.intervalSeconds, 1, 3600, 60),
      maxWallMinutes: clampInteger(body.maxWallMinutes, 1, 1440, 120),
      goalBriefPaths: cleanStringList(body.goalBriefPaths),
      safetyPolicyPaths: cleanStringList(body.safetyPolicyPaths),
      evidencePaths: cleanStringList(body.evidencePaths),
      evidenceIndexPaths: cleanStringList(body.evidenceIndexPaths),
      repoSearchPaths: cleanStringList(body.repoSearchPaths),
      webEvidenceUrls: cleanStringList(body.webEvidenceUrls),
      webCrawlDepth: clampInteger(body.webCrawlDepth, 0, 2, 0),
      webSearchQueries: cleanStringList(body.webSearchQueries),
      webSearchFetch: Boolean(body.webSearchFetch),
      webSearchCrawlDepth: clampInteger(body.webSearchCrawlDepth, 0, 2, 0),
      literatureSearchQueries: cleanStringList(body.literatureSearchQueries),
      literatureFullText: Boolean(body.literatureFullText),
      capabilityEvaluationPaths: cleanStringList(body.capabilityEvaluationPaths),
      preferenceReviewPaths: cleanStringList(body.preferenceReviewPaths),
      prospectiveEvaluationPaths: cleanStringList(body.prospectiveEvaluationPaths),
      feedbackLoopEvaluationPaths: cleanStringList(body.feedbackLoopEvaluationPaths),
      feedbackLoopReviewPaths: cleanStringList(body.feedbackLoopReviewPaths),
      agentRetrieval: Boolean(body.agentRetrieval),
      toolBudget: clampInteger(body.toolBudget, 0, 1000, 0),
      agentValidationManifestPaths: cleanStringList(body.agentValidationManifestPaths),
      agentRetrievalIterations: clampInteger(body.agentRetrievalIterations, 1, 10, 2),
      agentFetchDomains: cleanStringList(body.agentFetchDomains),
      reviewProcesses: clampInteger(body.reviewProcesses, 0, 32, 0),
      providerCallBudget: clampInteger(body.providerCallBudget, 1, 10000, 100),
      pdfVision: Boolean(body.pdfVision),
      pdfVisionMaxRegions: clampInteger(body.pdfVisionMaxRegions, 0, 100, 10),
      pdfVisionCallBudget: clampInteger(body.pdfVisionCallBudget, 1, 1000, 10),
      runName: sanitizeRunName(String(body.runName ?? ""))
    });
    return NextResponse.json({ run });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to start run" },
      { status: mutationErrorStatus(error) }
    );
  }
}

function cleanStringList(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}
