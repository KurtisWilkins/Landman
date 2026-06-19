import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Pipeline } from "./Pipeline";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const ROW = {
  acquisition_id: "dl_1",
  name: "Cedar Hollow",
  property_type: "rv_resort",
  current_phase: "loi",
  status: "active",
  ask_price: "5000000",
  site_count: 120,
  city: "Bend",
  state: "OR",
  blocking_gate_count: 0,
  returns: {
    going_in_cap: 0.07,
    loan_amount: 3250000,
    ltv: 0.65,
    hold_years: 5,
    equity: 1750000,
    promote_value: 16015117,
    partner_irr: 0.175,
    partner_moic: 2.13,
    rjourney_irr: 0.276,
    rjourney_moic: 3.19,
    deal_irr: 0.186,
    deal_moic: 2.23,
  },
};

function renderPipeline() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Pipeline />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Pipeline", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) =>
        String(url).includes("/acquisitions") ? jsonResponse([ROW]) : jsonResponse([], 200),
      ),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lists acquisitions with headline return columns", async () => {
    renderPipeline();
    expect(await screen.findByRole("link", { name: "Cedar Hollow" })).toBeInTheDocument();
    // Headline promote columns, formatted as "IRR · MOIC".
    expect(screen.getByText("17.5% · 2.13x")).toBeInTheDocument(); // Partner
    expect(screen.getByText("27.6% · 3.19x")).toBeInTheDocument(); // RJourney
    expect(screen.getByText("18.6% · 2.23x")).toBeInTheDocument(); // Deal-Level
    expect(screen.getByText("$16,015,117")).toBeInTheDocument(); // promote value
  });
});
