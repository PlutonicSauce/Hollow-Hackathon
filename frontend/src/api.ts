import type {
  Evaluation,
  OptimizationPolicy,
  Receipt,
  Scenario,
  ScenarioChoice,
  VerificationReport,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    // Hosting proxies can return HTML during a cold start or upstream failure.
    // Never expose their body or a JSON parser exception in the product.
    throw new Error(
      response.ok
        ? "The server returned an unreadable response. Try again shortly."
        : `Request failed (${response.status}). Try again shortly.`,
    );
  }
  if (!response.ok) {
    const message =
      typeof body === "object" &&
      body !== null &&
      "error" in body &&
      typeof body.error === "string"
        ? body.error
        : `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return body as T;
}

export const api = {
  scenarios: () => request<ScenarioChoice[]>("/api/scenarios"),
  scenario: (key: string) => request<Scenario>(`/api/scenarios/${key}`),
  evaluate: (scenario: Scenario, policy?: OptimizationPolicy) =>
    request<Evaluation>("/api/evaluate", {
      method: "POST",
      body: JSON.stringify({ scenario, policy }),
    }),
  verify: (receipt: Receipt) =>
    request<VerificationReport>("/api/verify", {
      method: "POST",
      body: JSON.stringify({ receipt }),
    }),
};

export type { OptimizationPolicy };
