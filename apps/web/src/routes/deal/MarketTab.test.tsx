import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarketTab } from "./MarketTab";

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MarketTab dealId="dl_1" />
    </QueryClientProvider>,
  );
}

describe("MarketTab", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              rings: [
                { radius_mi: 25, population: 42000, is_override: true, overridden_by: "kurtis" },
                { radius_mi: 50, population: 50000, is_override: false, source: "census" },
                { radius_mi: 100, population: 100000, is_override: false, source: "census" },
                { radius_mi: 150, population: 150000, is_override: false, source: "census" },
              ],
            }),
            { status: 200 },
          ),
      ),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders the four rings with populations and flags overrides", async () => {
    renderTab();
    for (const label of ["25 mi", "50 mi", "100 mi", "150 mi"]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("42,000")).toBeInTheDocument();
    expect(screen.getByText("150,000")).toBeInTheDocument();
    expect(screen.getByText("override")).toBeInTheDocument(); // the 25-mi ring
  });
});
