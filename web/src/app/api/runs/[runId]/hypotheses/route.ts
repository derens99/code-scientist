import { NextResponse } from "next/server";
import { appendManualHypothesis } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await appendManualHypothesis(runId, {
      title: String(body.title ?? ""),
      claim: String(body.claim ?? ""),
      rationale: String(body.rationale ?? ""),
      assumptions: toStringList(body.assumptions),
      evidenceRefs: toStringList(body.evidenceRefs),
      experiment: String(body.experiment ?? ""),
      metrics: toStringList(body.metrics),
      successCondition: String(body.successCondition ?? ""),
      risks: toStringList(body.risks)
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to save hypothesis" },
      { status: 400 }
    );
  }
}

function toStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
