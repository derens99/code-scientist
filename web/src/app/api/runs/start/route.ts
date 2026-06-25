import { NextResponse } from "next/server";
import { clampInteger, sanitizeRunName, startRun } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const run = await startRun({
      objective: String(body.objective ?? ""),
      cycles: clampInteger(body.cycles, 1, 5, 1),
      maxHypotheses: clampInteger(body.maxHypotheses, 2, 20, 6),
      maxMatches: clampInteger(body.maxMatches, 0, 40, 4),
      provider: body.provider === "anthropic" ? "anthropic" : "deterministic",
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
      runName: sanitizeRunName(String(body.runName ?? ""))
    });
    return NextResponse.json({ run });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to start run" },
      { status: 400 }
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
