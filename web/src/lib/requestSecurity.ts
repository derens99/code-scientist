export class MutationRequestError extends Error {}

export function assertTrustedMutationRequest(request: Request): void {
  const fetchSite = request.headers.get("sec-fetch-site")?.toLowerCase();
  if (fetchSite === "cross-site") {
    throw new MutationRequestError("Cross-site mutation requests are not allowed.");
  }

  const origin = request.headers.get("origin");
  if (!origin) {
    return;
  }
  let requestUrl: URL;
  let originUrl: URL;
  try {
    requestUrl = new URL(request.url);
    originUrl = new URL(origin);
  } catch {
    throw new MutationRequestError("Mutation request origin is invalid.");
  }
  if (requestUrl.protocol !== originUrl.protocol || requestUrl.host !== originUrl.host) {
    throw new MutationRequestError("Mutation request origin does not match this workbench.");
  }
}

export function mutationErrorStatus(error: unknown): number {
  return error instanceof MutationRequestError ? 403 : 400;
}
