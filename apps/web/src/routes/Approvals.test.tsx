import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Approvals } from "./Approvals";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderApprovals() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Approvals />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Approvals", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (method === "GET" && url.includes("/question-suggestions")) {
          return jsonResponse([
            {
              suggestion_id: "qs_1",
              phase: "due_diligence",
              type: "add",
              text: "Confirm septic capacity.",
              status: "pending",
            },
          ]);
        }
        if (method === "PATCH") return jsonResponse({ suggestion_id: "qs_1", status: "approved" });
        return jsonResponse([], 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lists pending suggestions and approves one", async () => {
    const user = userEvent.setup();
    renderApprovals();
    expect(await screen.findByText("Confirm septic capacity.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => {
      const patchCall = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        ([u, init]) => (init as RequestInit)?.method === "PATCH" && String(u).includes("qs_1"),
      );
      expect(patchCall).toBeTruthy();
      expect(JSON.parse((patchCall![1] as RequestInit).body as string)).toEqual({
        status: "approved",
      });
    });
  });
});
