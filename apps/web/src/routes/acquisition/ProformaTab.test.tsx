import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProformaTab } from "./ProformaTab";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const RESULTS = {
  years: [
    {
      yr: 1,
      revenue: 1200000,
      opex: 500000,
      noi: 700000,
      debt_service: 400000,
      capex: 0,
      levered_cf: 300000,
    },
  ],
  exit: { year: 5, net_proceeds: 8000000 },
  levered_irr: 0.18,
  equity_multiple: 2.1,
  equity_basis: 3500000,
};

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ProformaTab acquisitionId="dl_1" />
    </QueryClientProvider>,
  );
}

describe("ProformaTab", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/proforma-inputs")) {
          if (init?.method === "PUT") return jsonResponse(RESULTS);
          return jsonResponse({}); // GET inputs: none saved -> form uses defaults
        }
        if (u.includes("/proforma")) return jsonResponse(RESULTS);
        return jsonResponse({}, 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("seeds debt defaults and renders the computed pro forma", async () => {
    renderTab();
    // LTV default 0.65 displayed as 65.
    expect(await screen.findByLabelText("LTV")).toHaveValue(65);
    expect(screen.getByLabelText("Amortization (months)")).toHaveValue(360);
    // Results table from the persisted pro forma (awaits the proforma query).
    expect(await screen.findByText("Levered CF")).toBeInTheDocument();
    expect(screen.getByText(/Equity required/)).toBeInTheDocument();
  });

  it("PUTs the assumptions on save & recompute", async () => {
    const user = userEvent.setup();
    renderTab();
    const rev = await screen.findByLabelText("Revenue");
    await user.clear(rev);
    await user.type(rev, "1200000");
    await user.click(screen.getByRole("button", { name: /save & recompute/i }));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
      );
      expect(put).toBeTruthy();
      const body = JSON.parse((put![1] as RequestInit).body as string);
      expect(body.stabilized_revenue).toBe(1200000);
      expect(body.ltv).toBe(0.65); // debt sized on the pro forma, not the promote
    });
  });
});
