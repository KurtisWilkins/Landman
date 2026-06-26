import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PromoteTab } from "./PromoteTab";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const pos = (label: string, irr: string, moic: string, equity: string, profit: string) => ({
  label,
  cashflows: ["-150000000", "7500000", "7875000", "8268750", "8682188", "302760047"],
  equity,
  profit,
  irr,
  moic,
});

const RESULT = {
  acquisition_name: "Horseshoe Bend RV Resort",
  dates: ["2025-12-31", "2026-12-31", "2027-12-31", "2028-12-31", "2029-12-31", "2030-12-31"],
  purchase_price: "428571429",
  acquisition_fee: "0",
  acquisition_cashflows: ["-150000000", "7500000", "7875000", "8268750", "8682188", "302760047"],
  combined_equity_distributions: ["0", "0", "0", "0", "0", "169070867"],
  rjourney_carried_interest: ["0", "0", "0", "0", "0", "16015117"],
  total_promote: "16015117",
  tiers: [
    {
      tier: 1,
      hurdle_rate: "0.08",
      promote_pct: "0",
      equity_total: "63622050",
      carry_total: "0",
      irr_check: "0.08",
      binds: true,
    },
    {
      tier: 2,
      hurdle_rate: "0.15",
      promote_pct: "0.10",
      equity_total: "74499027",
      carry_total: "8277670",
      irr_check: "0.15",
      binds: true,
    },
    {
      tier: 3,
      hurdle_rate: "0.20",
      promote_pct: "0.20",
      equity_total: "30949790",
      carry_total: "7737448",
      irr_check: "0.1745",
      binds: false,
    },
    {
      tier: 4,
      hurdle_rate: "0.20",
      promote_pct: "0.30",
      equity_total: "0",
      carry_total: "0",
      irr_check: "0.1745",
      binds: false,
    },
  ],
  acquisition: pos("Acquisition-Level", "0.18639", "2.2339", "150000000", "185085984"),
  partner: pos("Partner Equity", "0.17450", "2.1271", "135000000", "152163780"),
  rjourney: pos("RJourney Equity", "0.27599", "3.1948", "15000000", "32922204"),
  cashflow_ties_out: true,
};

const DEAL = {
  acquisition_id: "dl_1",
  metadata: {
    name: "Horseshoe Bend RV Resort",
    current_phase: "initial_uw",
    status: "active",
    purchase_price: "428571429",
  },
  market: { rings: [] },
};

// A pro forma that yields the same acquisition-level stream as RESULT.acquisition_cashflows.
const PROFORMA = {
  years: [
    { yr: 1, levered_cf: "7500000" },
    { yr: 2, levered_cf: "7875000" },
    { yr: 3, levered_cf: "8268750" },
    { yr: 4, levered_cf: "8682188" },
    { yr: 5, levered_cf: "8682188" },
  ],
  exit: { year: 5, net_proceeds: "294077859" },
  levered_irr: "0.186",
  equity_multiple: "2.23",
  equity_basis: "150000000",
};

const EMPTY_PROFORMA = { years: [], exit: null, equity_basis: null };

function mockFetch(proforma: unknown) {
  return vi.fn(async (url: string | URL) => {
    const u = String(url);
    if (u.includes("/promote/waterfall")) return jsonResponse(RESULT);
    if (u.includes("/proforma")) return jsonResponse(proforma);
    if (u.includes("/acquisitions/")) return jsonResponse(DEAL);
    return jsonResponse({}, 404);
  });
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <PromoteTab acquisitionId="dl_1" />
    </QueryClientProvider>,
  );
}

function lastPostBody() {
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const post = fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === "POST")
    .at(-1)!;
  return JSON.parse((post[1] as RequestInit).body as string);
}

afterEach(() => vi.unstubAllGlobals());

describe("PromoteTab — pro-forma-fed", () => {
  beforeEach(() => vi.stubGlobal("fetch", mockFetch(PROFORMA)));

  it("derives the acquisition stream from the pro forma and shows genericized positions", async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText("27.6%")).toBeInTheDocument()); // RJourney IRR
    expect(screen.getByText("3.19x")).toBeInTheDocument();
    expect(screen.getAllByText("Partner Equity").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RJourney Equity").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Fund 21/)).not.toBeInTheDocument();
    expect(screen.getByText("$16,015,117")).toBeInTheDocument();

    // The acquisition basis (price/equity/debt/LTV) flows in from the pro forma and is displayed.
    expect(screen.getByText(/Acquisition basis/)).toBeInTheDocument();
    expect(screen.getByText("$278,571,429")).toBeInTheDocument(); // debt = price − equity
    expect(screen.getByText("65.0%")).toBeInTheDocument(); // implied LTV = 1 − equity/price

    // Banner indicates pro-forma sourcing; the return-case equity field is hidden.
    expect(screen.getByText(/Cash flows are sourced/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Total equity")).not.toBeInTheDocument();
    // Debt lives on the pro forma — no LTV/debt input on the promote tab.
    expect(screen.queryByLabelText("Asset LTV")).not.toBeInTheDocument();

    // The POST fed the engine the pro-forma-derived stream via cashflow_override.
    const body = lastPostBody();
    expect(body.cashflow_override).toEqual([
      -150000000, 7500000, 7875000, 8268750, 8682188, 302760047,
    ]);
    expect(body.equity).toBe(150000000);
    expect(body.hold_years).toBe(5);
    expect(body.acquisition_name).toBe("Horseshoe Bend RV Resort");
  });

  it("recalculates when a promote-specific input changes", async () => {
    const user = userEvent.setup();
    renderTab();
    await waitFor(() => expect(screen.getByText("27.6%")).toBeInTheDocument());
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const before = fetchMock.mock.calls.length;

    await user.clear(screen.getByLabelText("RJourney co-invest"));
    await user.type(screen.getByLabelText("RJourney co-invest"), "20");

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    expect(lastPostBody().rjourney_coinvest_pct).toBe(0.2);
  });
});

describe("PromoteTab — interim fallback (no pro forma)", () => {
  beforeEach(() => vi.stubGlobal("fetch", mockFetch(EMPTY_PROFORMA)));

  it("uses editable return-case assumptions and sends no cashflow_override", async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText("27.6%")).toBeInTheDocument());
    expect(screen.getByText(/No pro forma for this acquisition yet/)).toBeInTheDocument();
    // The return-case equity field is available in fallback mode.
    expect(screen.getByLabelText("Total equity")).toBeInTheDocument();

    const body = lastPostBody();
    expect(body.cashflow_override).toBeNull();
    expect(body.equity).toBe(150000000);
    expect(body.hold_years).toBe(5);
  });
});
