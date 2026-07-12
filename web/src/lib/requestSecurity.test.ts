import { describe, expect, it } from "vitest";
import { assertTrustedMutationRequest, mutationErrorStatus } from "./requestSecurity";

describe("assertTrustedMutationRequest", () => {
  it("accepts same-origin browser mutations and non-browser clients", () => {
    expect(() =>
      assertTrustedMutationRequest(
        new Request("http://127.0.0.1:3000/api/runs/start", {
          method: "POST",
          headers: { origin: "http://127.0.0.1:3000", "sec-fetch-site": "same-origin" }
        })
      )
    ).not.toThrow();
    expect(() =>
      assertTrustedMutationRequest(
        new Request("http://127.0.0.1:3000/api/runs/start", { method: "POST" })
      )
    ).not.toThrow();
  });

  it("rejects cross-site and mismatched-origin mutations with 403", () => {
    const rejectedHeaders: Array<Record<string, string>> = [
      { "sec-fetch-site": "cross-site" },
      { origin: "https://attacker.example" }
    ];
    for (const headers of rejectedHeaders) {
      try {
        assertTrustedMutationRequest(
          new Request("http://127.0.0.1:3000/api/runs/start", { method: "POST", headers })
        );
        throw new Error("expected request to be rejected");
      } catch (error) {
        expect(mutationErrorStatus(error)).toBe(403);
      }
    }
  });
});
