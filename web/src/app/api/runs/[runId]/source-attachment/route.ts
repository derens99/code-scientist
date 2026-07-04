import { NextResponse } from "next/server";
import { appendSourceAttachments } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    const body = await request.json();
    const state = await appendSourceAttachments(runId, {
      evidencePaths: toStringList(body.evidencePaths),
      evidenceIndexPaths: toStringList(body.evidenceIndexPaths)
    });
    return NextResponse.json({ state });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to attach sources" },
      { status: 400 }
    );
  }
}

function toStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
