import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UnderwritingTab } from "./UnderwritingTab";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const DOC = {
  acquisition_id: "dl_1",
  metadata: {
    name: "Cedar Hollow",
    property_type: "rv_resort",
    address: { city: "Bend", state: "OR" },
    site_count: 120,
    ask_price: "5000000",
    purchase_price: null,
    seller_name: "Hollow LLC",
    current_phase: "loi",
    status: "active",
  },
};

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <UnderwritingTab acquisitionId="dl_1" />
    </QueryClientProvider>,
  );
}

describe("UnderwritingTab", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        jsonResponse(init?.method === "PATCH" ? { ...DOC } : DOC),
      ),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows OM details and seeds purchase price from the ask when unset", async () => {
    renderTab();
    expect(await screen.findByText("Cedar Hollow")).toBeInTheDocument();
    expect(screen.getByText("Bend, OR")).toBeInTheDocument();
    // purchase_price is null -> input falls back to the OM ask (5000000).
    expect(screen.getByLabelText("Purchase price")).toHaveValue("5000000");
  });

  it("PATCHes the negotiated purchase price on save", async () => {
    const user = userEvent.setup();
    renderTab();
    const input = await screen.findByLabelText("Purchase price");
    await user.clear(input);
    await user.type(input, "4250000");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PATCH",
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse((patch![1] as RequestInit).body as string)).toEqual({
        purchase_price: "4250000",
      });
    });
  });
});
