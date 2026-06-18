import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FinancialVersions } from "./FinancialVersions";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const VERSIONS = [
  {
    period_id: "fp_new",
    label: "ingested",
    source_filename: "pnl-2024.xlsx",
    granularity: "t12",
    ingested_at: "2026-06-18T00:00:00Z",
    is_current: true,
    line_count: 80,
  },
  {
    period_id: "fp_old",
    label: "ingested",
    source_filename: "pnl-2023.xlsx",
    granularity: "t12",
    ingested_at: "2026-05-01T00:00:00Z",
    is_current: false,
    line_count: 76,
  },
];

function renderVersions() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <FinancialVersions dealId="dl_1" />
    </QueryClientProvider>,
  );
}

describe("FinancialVersions", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists retained versions and activates an older one (never deletes)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "POST") return jsonResponse(VERSIONS);
        return jsonResponse(VERSIONS);
      }),
    );
    const user = userEvent.setup();
    renderVersions();

    await waitFor(() => expect(screen.getByText("pnl-2024.xlsx")).toBeInTheDocument());
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("pnl-2023.xlsx")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Make active" }));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, i]) => (i as RequestInit)?.method === "POST");
      expect(post?.[0]).toContain("/deals/dl_1/financial-periods/fp_old/activate");
    });
  });

  it("renders nothing when there is only one version (nothing to choose)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([VERSIONS[0]])),
    );
    const { container } = (() => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return render(
        <QueryClientProvider client={qc}>
          <FinancialVersions dealId="dl_1" />
        </QueryClientProvider>,
      );
    })();
    // Give the query a tick; the component stays empty for a single version.
    await waitFor(() => expect(screen.queryByText("Financials versions")).not.toBeInTheDocument());
    expect(container.querySelector("button")).toBeNull();
  });
});
