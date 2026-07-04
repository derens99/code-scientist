import { NextResponse } from "next/server";
import { appendEvaluationReturns } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await appendEvaluationReturns(runId, {
      capabilityEvaluationPaths: toStringList(body.capabilityEvaluationPaths),
      capabilityReviewPaths: toStringList(body.capabilityReviewPaths),
      preferenceReviewPaths: toStringList(body.preferenceReviewPaths),
      prospectiveEvaluationPaths: toStringList(body.prospectiveEvaluationPaths),
      feedbackLoopEvaluationPaths: toStringList(body.feedbackLoopEvaluationPaths),
      feedbackLoopReviewPaths: toStringList(body.feedbackLoopReviewPaths)
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to attach evaluation returns" },
      { status: 400 }
    );
  }
}

function toStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
