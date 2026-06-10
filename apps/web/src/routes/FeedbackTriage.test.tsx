import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackTriage } from "./FeedbackTriage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderTriage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FeedbackTriage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FeedbackTriage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (method === "GET" && url.includes("/feedback")) {
          return jsonResponse([
            {
              feedback_id: "fb_1",
              type: "bug",
              title: "Pro forma blank",
              status: "ready",
              page_route: "/deals/dl_1/proforma",
            },
          ]);
        }
        if (method === "POST" && url.includes("/dispatch")) {
          return jsonResponse({ dispatch_id: "fd_1", feedback_id: "fb_1", status: "issue_open" });
        }
        return jsonResponse([], 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lists items and dispatches a ready item", async () => {
    const user = userEvent.setup();
    renderTriage();
    expect(await screen.findByText("Pro forma blank")).toBeInTheDocument();

    const dispatchBtn = screen.getByRole("button", { name: /dispatch/i });
    expect(dispatchBtn).toBeEnabled();
    await user.click(dispatchBtn);
    await waitFor(() => {
      const call = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        ([u, init]) =>
          (init as RequestInit)?.method === "POST" && String(u).includes("/feedback/fb_1/dispatch"),
      );
      expect(call).toBeTruthy();
    });
  });
});
