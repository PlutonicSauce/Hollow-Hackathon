import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("HTTP failure recovery", () => {
  it.each([503, 200])("does not expose a proxy body or parser error (HTTP %s)", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      "<html>upstream diagnostic /private/server/path</html>", { status },
    )));
    await expect(api.scenarios()).rejects.toThrow(
      status === 200
        ? "The server returned an unreadable response. Try again shortly."
        : "Request failed (503). Try again shortly.",
    );
  });

  it("preserves the public API's actionable JSON error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: "One computation is already running. Retry shortly." }),
      { status: 503 },
    )));
    await expect(api.scenarios()).rejects.toThrow("One computation is already running. Retry shortly.");
  });
});
