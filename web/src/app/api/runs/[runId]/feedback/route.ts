import { NextResponse } from "next/server";
import { appendUserFeedback } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await appendUserFeedback(runId, {
      targetId: String(body.targetId ?? ""),
      kind: String(body.kind ?? "preference"),
      content: String(body.content ?? ""),
      influence: String(body.influence ?? "informational")
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to save feedback" },
      { status: 400 }
    );
  }
}
