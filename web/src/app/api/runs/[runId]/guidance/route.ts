import { NextResponse } from "next/server";
import { updateRunGuidance } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await updateRunGuidance(runId, {
      preferences: toStringList(body.preferences),
      constraints: toStringList(body.constraints),
      allowedSources: toStringList(body.allowedSources),
      followUpDirection: String(body.followUpDirection ?? "")
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to update guidance" },
      { status: 400 }
    );
  }
}

function toStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
