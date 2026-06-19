import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Settings />
    </QueryClientProvider>,
  );
}

const ANTHROPIC = "Anthropic API key (PDF/OM extraction, AI)";
const LIST = [
  { key: "anthropic_api_key", label: ANTHROPIC, configured: false, source: null, hint: null },
  {
    key: "voyage_api_key",
    label: "Voyage embeddings key (GL mapping)",
    configured: true,
    source: "environment",
    hint: "6789",
  },
];

describe("Settings", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "GET" && url.includes("/admin/integrations"))
          return jsonResponse(LIST);
        if (init?.method === "PUT")
          return jsonResponse({
            key: "anthropic_api_key",
            label: ANTHROPIC,
            configured: true,
            source: "database",
            hint: "WXYZ",
          });
        return jsonResponse([], 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows configured/missing status and saves a key (write-only)", async () => {
    const user = userEvent.setup();
    renderSettings();

    await waitFor(() => expect(screen.getByText("Missing")).toBeInTheDocument());
    expect(screen.getByText(/Configured \(…6789\)/)).toBeInTheDocument();

    await user.type(screen.getByLabelText(`${ANTHROPIC} value`), "sk-ant-newkeyWXYZ");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const put = fetchMock.mock.calls.find(([, i]) => (i as RequestInit)?.method === "PUT")!;
    expect(put[0]).toContain("/admin/integrations/anthropic_api_key");
    expect(JSON.parse((put[1] as RequestInit).body as string)).toEqual({
      value: "sk-ant-newkeyWXYZ",
    });
  });

  it("edits and saves underwriting defaults", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes("/underwriting-defaults")) {
          if (init?.method === "PUT") return jsonResponse({ ltv: 0.7, amort_months: 360 });
          return jsonResponse({
            ltv: 0.65,
            loan_rate: 0.065,
            noi_growth: 0.03,
            exit_cap: 0.07,
            selling_cost_rate: 0.02,
            capex_reserve_rate: 0,
            amort_months: 360,
            io_years: 0,
            hold_years: 5,
          });
        }
        if (url.includes("/admin/integrations")) return jsonResponse(LIST);
        return jsonResponse([], 200);
      }),
    );
    const user = userEvent.setup();
    renderSettings();

    const ltv = await screen.findByLabelText("LTV");
    await waitFor(() => expect(ltv).toHaveValue(65)); // 0.65 shown as 65
    // Single change event avoids the controlled ×100 input race that clear+type hits.
    fireEvent.change(ltv, { target: { value: "70" } });
    await user.click(screen.getByRole("button", { name: "Save defaults" }));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([u, i]) =>
          String(u).includes("/underwriting-defaults") && (i as RequestInit)?.method === "PUT",
      );
      expect(put).toBeTruthy();
      expect(JSON.parse((put![1] as RequestInit).body as string).ltv).toBe(0.7);
    });
  });

  it("shows an admin-only notice on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { code: "forbidden", message: "no" } }, 403)),
    );
    renderSettings();
    await waitFor(() => expect(screen.getByText(/admin-only/i)).toBeInTheDocument());
  });
});
