import React from "react";
import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RunSetup } from "./RunSetup";

describe("RunSetup", () => {
  it("renders source corpus selectors for evidence, indexes, repository search, web search, literature queries, full text, and evaluation fixtures", () => {
    const markup = renderToStaticMarkup(
      React.createElement(
        MantineProvider,
        {},
        React.createElement(RunSetup, {
          onRunCreated: () => undefined,
          onError: () => undefined
        })
      )
    );

    expect(markup).toContain("Goal brief paths");
    expect(markup).toContain("Safety policy paths");
    expect(markup).toContain("Evidence paths");
    expect(markup).toContain("Evidence index paths");
    expect(markup).toContain("Repository search paths");
    expect(markup).toContain("Web evidence URLs");
    expect(markup).toContain("Web crawl depth");
    expect(markup).toContain("Web search queries");
    expect(markup).toContain("Fetch web search result pages");
    expect(markup).toContain("Web search crawl depth");
    expect(markup).toContain("Literature search queries");
    expect(markup).toContain("Fetch literature full text");
    expect(markup).toContain("Capability evaluation fixtures");
    expect(markup).toContain("Preference-review fixtures");
    expect(markup).toContain("Prospective evaluation fixtures");
    expect(markup).toContain("Feedback-loop evaluation fixtures");
    expect(markup).toContain("Feedback-loop blind review fixtures");
    expect(markup).toContain("Agent-driven iterative retrieval");
    expect(markup).toContain("Agent tool budget");
    expect(markup).toContain("Agent validation manifest paths");
    expect(markup).toContain("Retrieval iterations per task");
    expect(markup).toContain("Agent fetch domains");
    expect(markup).toContain("Review worker processes");
  });
});
