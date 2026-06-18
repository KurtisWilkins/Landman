import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewAcquisitionForm } from "./NewAcquisitionForm";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const OM_PROPOSAL = {
  name: "Cedar Ridge RV",
  property_type: "campground",
  address: { city: "Austin", state: "TX" },
  site_count: 120,
  ask_price: "4500000",
  seller_name: null,
  financial_lines: [{ description: "Rental Income", amount: "520000" }],
};

function renderForm(onCreated = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <NewAcquisitionForm onCreated={onCreated} onCancel={vi.fn()} />
    </QueryClientProvider>,
  );
  return { onCreated };
}

describe("NewAcquisitionForm", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/acquisitions/extract-om")) return jsonResponse(OM_PROPOSAL, 200);
        if (url.includes("/documents")) return jsonResponse({ status: "loaded" }, 202);
        if (url.includes("/acquisitions"))
          return jsonResponse(
            { acquisition_id: "dl_new123", metadata: {}, market: { rings: [] } },
            201,
          );
        return jsonResponse([], 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("submits the entered fields and reports the new acquisition id", async () => {
    const user = userEvent.setup();
    const { onCreated } = renderForm();

    await user.type(screen.getByLabelText("Property name"), "Cedar Ridge RV");
    await user.selectOptions(screen.getByLabelText("Property type"), "campground");
    await user.type(screen.getByLabelText("City"), "Austin");
    await user.type(screen.getByLabelText("Ask price (USD)"), "4500000");
    await user.click(screen.getByRole("button", { name: "Create acquisition" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("dl_new123"));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const createCall = fetchMock.mock.calls.find(
      ([u, init]) => u.includes("/acquisitions") && (init as RequestInit)?.method === "POST",
    )!;
    const body = JSON.parse((createCall[1] as RequestInit).body as string);
    expect(body).toMatchObject({
      name: "Cedar Ridge RV",
      property_type: "campground",
      address: { city: "Austin" },
      ask_price: "4500000", // money sent as a string, never a float
    });
  });

  it("disables submit until a name is entered", () => {
    renderForm();
    expect(screen.getByRole("button", { name: "Create acquisition" })).toBeDisabled();
  });

  it("OM mode extracts a proposal and pre-fills the form for review", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("tab", { name: "Upload OM (PDF)" }));
    const pdf = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "om.pdf", {
      type: "application/pdf",
    });
    await user.upload(screen.getByLabelText("Offering memorandum"), pdf);
    await user.click(screen.getByRole("button", { name: "Extract from OM" }));

    // Fields are pre-filled from the proposal, and the extracted financials are previewed.
    await waitFor(() =>
      expect(screen.getByLabelText("Property name")).toHaveValue("Cedar Ridge RV"),
    );
    expect(screen.getByLabelText("Ask price (USD)")).toHaveValue("4500000");
    expect(screen.getByText("Rental Income")).toBeInTheDocument();

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some(([u]) => u.includes("/acquisitions/extract-om"))).toBe(true);
  });
});
