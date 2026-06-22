import { NextResponse } from "next/server";
import { readRunReport } from "@/lib/codeScientist";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await params;
    return new NextResponse(await readRunReport(runId), {
      headers: { "content-type": "text/markdown; charset=utf-8" }
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to read report" },
      { status: 404 }
    );
  }
}
