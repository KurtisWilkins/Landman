import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GLDocsTab } from "./GLDocsTab";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const MAPPING = {
  acquisition_id: "dl_1",
  lines: [
    {
      line_id: "fl1",
      seller_source_line: "Site Rent",
      amount: 5000,
      proposed_account_code: null,
      proposed_account_name: null,
      proposed_level: null,
      map_confidence: "unmapped",
      map_confidence_score: null,
      noi_placement: null,
      reviewed_at: null,
      candidates: [],
    },
  ],
};

const ACCOUNTS = [
  {
    account_code: "4000",
    name: "Site revenue",
    level: "leaf",
    section: "Income",
    noi_placement: "above",
  },
];

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <GLDocsTab acquisitionId="dl_1" />
    </QueryClientProvider>,
  );
}

describe("GLDocsTab mapping workstation", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const u = String(url);
        if (u.includes("/mapping/confirm")) return jsonResponse(MAPPING);
        if (u.includes("/gl-accounts")) return jsonResponse(ACCOUNTS);
        if (u.endsWith("/mapping")) return jsonResponse(MAPPING);
        return jsonResponse([]); // financial-periods, etc.
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("confirms an unmapped line against the chosen GL account", async () => {
    const user = userEvent.setup();
    renderTab();

    const select = await screen.findByLabelText("Account for Site Rent");
    await user.selectOptions(select, "4000");
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([u, init]) =>
          String(u).includes("/mapping/confirm") &&
          (init as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse((post![1] as RequestInit).body as string);
      expect(body.account_code).toBe("4000");
      expect(body.account_level).toBe("leaf"); // from the selected account
      expect(body.noi_placement).toBe("above"); // account default
      expect(body.learn).toBe(true);
    });
  });
});
