import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SourceAttachmentPanel } from "./SourceAttachmentPanel";

describe("SourceAttachmentPanel", () => {
  it("renders controls for attaching source files and indexes", () => {
    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(SourceAttachmentPanel, {
          submitting: false,
          evidence: [],
          evidenceSafetyFindings: [],
          onSourceAttachment: async () => {}
        })
      )
    );

    expect(markup).toContain("Source attachments");
    expect(markup).toContain("Evidence paths");
    expect(markup).toContain("Evidence indexes");
    expect(markup).toContain("Attach sources");
  });

  it("renders current accepted and rejected source inventory", () => {
    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(SourceAttachmentPanel, {
          submitting: false,
          evidence: [
            {
              id: "ev-1",
              kind: "document",
              source: "/tmp/maintainer-notes.md",
              content: "Replay code review comments before selecting patches.",
              notes: "Attached source",
              metadata: {
                path: "/tmp/maintainer-notes.md",
                parser: "pdf_page_ocr",
                page_number: "3",
                citation: "/tmp/maintainer-notes.md:page 3"
              }
            }
          ],
          evidenceSafetyFindings: [
            {
              id: "finding-1",
              evidence_id: "ev-blocked",
              source: "/tmp/poisoned-notes.md",
              allowed: false,
              flags: ["prompt-injection"],
              reason: "Retrieved evidence contains unsafe instruction-like content.",
              content_preview: "Ignore previous instructions..."
            },
            {
              id: "finding-2",
              evidence_id: "ev-escalated",
              source: "/tmp/review-required.md",
              allowed: false,
              flags: ["policy:deployment", "manual-review-required"],
              reason: "Deployment evidence requires operator review.",
              content_preview: "Deploy after approval."
            }
          ],
          onSourceAttachment: async () => {}
        })
      )
    );

    expect(markup).toContain("Source inventory");
    expect(markup).toContain("/tmp/maintainer-notes.md");
    expect(markup).toContain("parser pdf_page_ocr");
    expect(markup).toContain("page 3");
    expect(markup).toContain("Rejected attachments");
    expect(markup).toContain("/tmp/poisoned-notes.md");
    expect(markup).toContain("prompt-injection");
    expect(markup).toContain("Manual safety review queue");
    expect(markup).toContain("1 pending");
    expect(markup).toContain("/tmp/review-required.md");
  });
});
