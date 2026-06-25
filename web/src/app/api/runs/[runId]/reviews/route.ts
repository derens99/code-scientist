import { NextResponse } from "next/server";
import { appendManualReview } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await appendManualReview(runId, {
      hypothesisId: String(body.hypothesisId ?? ""),
      decision: String(body.decision ?? ""),
      strengths: toStringList(body.strengths),
      weaknesses: toStringList(body.weaknesses),
      safetyNotes: toStringList(body.safetyNotes),
      findings: toStringList(body.findings),
      evidenceRefs: toStringList(body.evidenceRefs),
      confidence: Number(body.confidence),
      requiresRevision: Boolean(body.requiresRevision)
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to save review" },
      { status: 400 }
    );
  }
}

function toStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
