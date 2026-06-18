import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Promote } from "./Promote";

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
  deal_name: "Deal 1",
  dates: ["2025-12-31", "2026-12-31", "2027-12-31", "2028-12-31", "2029-12-31", "2030-12-31"],
  purchase_price: "428571429",
  acquisition_fee: "0",
  deal_cashflows: ["-150000000", "7500000", "7875000", "8268750", "8682188", "302760047"],
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
  deal: pos("Deal-Level", "0.18639", "2.2339", "150000000", "185085984"),
  partner: pos("Partner Equity", "0.17450", "2.1271", "135000000", "152163780"),
  rjourney: pos("RJourney Equity", "0.27599", "3.1948", "15000000", "32922204"),
  cashflow_ties_out: true,
};

function renderPromote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Promote />
    </QueryClientProvider>,
  );
}

describe("Promote", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(RESULT)),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("computes on mount and shows both genericized equity positions and the promote", async () => {
    renderPromote();
    // The reference returns render once the debounced POST resolves.
    await waitFor(() => expect(screen.getByText("27.6%")).toBeInTheDocument()); // RJourney IRR
    expect(screen.getByText("3.19x")).toBeInTheDocument(); // RJourney MOIC
    // Partner IRR 17.5% (also appears as the non-binding tier checks) — assert ≥1.
    expect(screen.getAllByText("17.5%").length).toBeGreaterThan(0);
    // Genericized labels only.
    expect(screen.getAllByText("Partner Equity").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RJourney Equity").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Fund 21/)).not.toBeInTheDocument();
    // Promote value surfaced.
    expect(screen.getByText("$16,015,117")).toBeInTheDocument();

    // The first POST carried the reference inputs.
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toContain("/promote/waterfall");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string).equity).toBe(150000000);
  });

  it("recalculates when an input changes", async () => {
    const user = userEvent.setup();
    renderPromote();
    await waitFor(() => expect(screen.getByText("27.6%")).toBeInTheDocument());
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const before = fetchMock.mock.calls.length;

    await user.clear(screen.getByLabelText("Total equity"));
    await user.type(screen.getByLabelText("Total equity"), "200000000");

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    const lastBody = JSON.parse((fetchMock.mock.calls.at(-1)![1] as RequestInit).body as string);
    expect(lastBody.equity).toBe(200000000);
  });
});
