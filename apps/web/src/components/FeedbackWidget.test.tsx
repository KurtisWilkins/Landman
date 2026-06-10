import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackWidget } from "./FeedbackWidget";

function renderWidget(route = "/deals/dl_42/proforma") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <FeedbackWidget />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FeedbackWidget", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ feedback_id: "fb_1", type: "bug", status: "new" }), {
            status: 201,
          }),
      ),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("submits a bug with silently-captured context and uses no browser storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    renderWidget();

    await user.click(screen.getByRole("button", { name: /send feedback/i }));
    await user.type(screen.getByLabelText(/description/i), "Pro forma is blank.");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.type).toBe("bug");
    expect(body.description).toBe("Pro forma is blank.");
    expect(body.context.page_route).toBe("/deals/dl_42/proforma");
    expect(body.context.deal_id).toBe("dl_42");
    // Bug reports include the diagnostic buffers.
    expect(body.context).toHaveProperty("breadcrumbs");
    // No browser storage for app state (CLAUDE.md).
    expect(setItem).not.toHaveBeenCalled();
  });

  it("disables send until a description is entered", async () => {
    const user = userEvent.setup();
    renderWidget("/");
    await user.click(screen.getByRole("button", { name: /send feedback/i }));
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
  });
});
