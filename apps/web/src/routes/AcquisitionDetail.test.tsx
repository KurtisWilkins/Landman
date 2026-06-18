import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcquisitionDetail } from "./AcquisitionDetail";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderAcquisition() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/acquisitions/dl_1"]}>
        <Routes>
          <Route path="/acquisitions/:acquisitionId" element={<AcquisitionDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AcquisitionDetail", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/acquisitions/dl_1"))
          return jsonResponse({
            acquisition_id: "dl_1",
            metadata: {
              name: "Cedar Hollow",
              property_type: "rv_resort",
              current_phase: "loi",
              status: "active",
            },
          });
        if (url.includes("/proforma"))
          return jsonResponse({
            years: [
              {
                yr: 1,
                revenue: 100,
                opex: 40,
                noi: 60,
                debt_service: 20,
                capex: 5,
                levered_cf: 35,
              },
            ],
            levered_irr: 0.19,
            equity_multiple: 2.1,
          });
        if (url.includes("/gate-questions")) return jsonResponse([]);
        return jsonResponse({}, 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the header and tabs, and renders pro forma rows", async () => {
    renderAcquisition();
    expect(await screen.findByRole("heading", { name: "Cedar Hollow" })).toBeInTheDocument();
    for (const t of ["Pro forma", "Comps", "Gates", "GL / Docs"]) {
      expect(screen.getByRole("tab", { name: t })).toBeInTheDocument();
    }
    // Pro forma is the default tab.
    expect(await screen.findByText("Levered CF")).toBeInTheDocument();
  });

  it("switches to the Gates tab", async () => {
    const user = userEvent.setup();
    renderAcquisition();
    await user.click(screen.getByRole("tab", { name: "Gates" }));
    expect(await screen.findByText(/no gate questions configured/i)).toBeInTheDocument();
  });
});
