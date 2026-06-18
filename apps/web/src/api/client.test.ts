import { describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  it("parses the structured error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: { code: "not_implemented", message: "stub" } }), {
            status: 501,
          }),
      ),
    );
    await expect(apiFetch("/acquisitions")).rejects.toMatchObject({
      status: 501,
      code: "not_implemented",
    });
    await expect(apiFetch("/acquisitions")).rejects.toBeInstanceOf(ApiError);
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ status: "ok" }), { status: 200 })),
    );
    await expect(apiFetch<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
  });
});
