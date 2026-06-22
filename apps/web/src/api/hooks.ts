/**
 * Typed server-state hooks (TanStack Query) against the generated §9 contract.
 * Data-fetching lives here; components stay presentational (CLAUDE.md).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "./types";
import { apiFetch, apiUpload, type Schemas } from "./client";

type AcquisitionSummary = Schemas["AcquisitionSummary"];
type AcquisitionDocument = Schemas["AcquisitionDocument"];
type AcquisitionCreate = Schemas["AcquisitionCreate"];
/** Result of POST /acquisitions/{id}/documents (endpoint returns an untyped dict, so typed here). */
export type UploadResult = {
  status: string;
  sheet_type: string;
  financial_lines_loaded: number;
  units_loaded: number;
};
type ProformaResults = Schemas["ProformaResults"];
type CompSet = Schemas["CompSet"];
type MappingReview = Schemas["MappingReview"];
type PopulationRingsDoc = Schemas["PopulationRingsDoc"];
type GateQuestion = Schemas["GateQuestion"];
type FeedbackOut = Schemas["FeedbackOut"];
type FeedbackCreate = Schemas["FeedbackCreate"];
type FeedbackPatch = Schemas["FeedbackPatch"];
type DispatchOut = Schemas["DispatchOut"];
type DispatchRequest = Schemas["DispatchRequest"];
type QuestionSuggestionOut = Schemas["QuestionSuggestionOut"];
type Phase = components["schemas"]["Phase"];
type FeedbackStatus = components["schemas"]["FeedbackStatus"];
type SuggestionStatus = components["schemas"]["SuggestionStatus"];

export function usePipeline(filters?: { phase?: Phase }) {
  const qs = filters?.phase ? `?phase=${filters.phase}` : "";
  return useQuery({
    queryKey: ["acquisitions", filters ?? {}],
    queryFn: () => apiFetch<AcquisitionSummary[]>(`/acquisitions${qs}`),
  });
}

export function useCreateAcquisition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AcquisitionCreate) =>
      apiFetch<AcquisitionDocument>("/acquisitions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["acquisitions"] }),
  });
}

type OmProposal = Schemas["OmProposal"];

export function useExtractOm() {
  // Extracts a reviewable proposal from an OM PDF (nothing is persisted server-side).
  return useMutation({
    mutationFn: (file: File) => apiUpload<OmProposal>("/acquisitions/extract-om", file),
  });
}

export function useUploadDocument(acquisitionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      apiUpload<UploadResult>(`/acquisitions/${acquisitionId}/documents`, file),
    onSuccess: () => {
      // The upload adds a new financials version + refreshes the mapping queue.
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "mapping"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "financial-periods"] });
    },
  });
}

type FinancialPeriodVersion = Schemas["FinancialPeriodVersion"];

export function useFinancialPeriods(acquisitionId: string) {
  // Dated, retained upload versions; the current one feeds the GL view.
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "financial-periods"],
    queryFn: () =>
      apiFetch<FinancialPeriodVersion[]>(`/acquisitions/${acquisitionId}/financial-periods`),
  });
}

export function useActivateFinancialPeriod(acquisitionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (periodId: string) =>
      apiFetch<FinancialPeriodVersion[]>(
        `/acquisitions/${acquisitionId}/financial-periods/${periodId}/activate`,
        { method: "POST" },
      ),
    onSuccess: () => {
      // Switching the active version changes which lines the GL view shows.
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "financial-periods"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "mapping"] });
    },
  });
}

type PromoteRequest = Schemas["PromoteRequest"];
type PromoteResponse = Schemas["PromoteResponse"];

export function usePromoteWaterfall() {
  // Stateless calculator: POST the inputs, get the full acquisition-by-acquisition promote result back.
  return useMutation({
    mutationFn: (body: PromoteRequest) =>
      apiFetch<PromoteResponse>("/promote/waterfall", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

type IntegrationStatus = Schemas["IntegrationStatus"];

export function useIntegrations() {
  return useQuery({
    queryKey: ["admin", "integrations"],
    queryFn: () => apiFetch<IntegrationStatus[]>("/admin/integrations"),
    retry: false, // a 403 (non-admin) shouldn't retry
  });
}

export function useSetIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      apiFetch<IntegrationStatus>(`/admin/integrations/${key}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "integrations"] }),
  });
}

type UnderwritingDefaults = Schemas["UnderwritingDefaults"];
type UnderwritingDefaultsOut = Schemas["UnderwritingDefaultsOut"];

export function useUnderwritingDefaults() {
  // Effective global pro-forma defaults (admin-set or built-in); seed new acquisitions' inputs.
  return useQuery({
    queryKey: ["underwriting-defaults"],
    queryFn: () => apiFetch<UnderwritingDefaultsOut>("/underwriting-defaults"),
  });
}

export function useSaveUnderwritingDefaults() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UnderwritingDefaults) =>
      apiFetch<UnderwritingDefaultsOut>("/underwriting-defaults", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["underwriting-defaults"] }),
  });
}

export function useAcquisition(acquisitionId: string) {
  return useQuery({
    queryKey: ["acquisition", acquisitionId],
    queryFn: () => apiFetch<AcquisitionDocument>(`/acquisitions/${acquisitionId}`),
  });
}

type AcquisitionUpdate = Schemas["AcquisitionUpdate"];

export function useUpdateAcquisition(acquisitionId: string) {
  // Edit underwriting-level fields (e.g. negotiated purchase price); refreshes the document.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AcquisitionUpdate) =>
      apiFetch<AcquisitionDocument>(`/acquisitions/${acquisitionId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      // A price edit re-sizes debt + re-runs the promote server-side. The prefix key below already
      // covers the proforma/returns children, but list them explicitly so the data-flow is clear.
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "proforma"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "returns"] });
      qc.invalidateQueries({ queryKey: ["acquisitions"] });
    },
  });
}

export function useProforma(acquisitionId: string) {
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "proforma"],
    queryFn: () => apiFetch<ProformaResults>(`/acquisitions/${acquisitionId}/proforma`),
  });
}

type ProformaMonthlyResults = Schemas["ProformaMonthlyResults"];

export function useProformaMonthly(acquisitionId: string) {
  // The 60-month grid; each 12-month block rolls up to the matching pro-forma year.
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "proforma-monthly"],
    queryFn: () =>
      apiFetch<ProformaMonthlyResults>(`/acquisitions/${acquisitionId}/proforma-monthly`),
  });
}

type AcquisitionReturns = Schemas["AcquisitionReturns"];

export function useAcquisitionReturns(acquisitionId: string) {
  // Headline returns (cap, loan/LTV, Partner/RJourney/Deal-Level IRR & MOIC) for the header.
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "returns"],
    queryFn: () => apiFetch<AcquisitionReturns>(`/acquisitions/${acquisitionId}/returns`),
  });
}

type ProformaInputs = Schemas["ProformaInputs"];
type ProformaInputsOut = Schemas["ProformaInputsOut"];

export function useProformaInputs(acquisitionId: string) {
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "proforma-inputs"],
    queryFn: () => apiFetch<ProformaInputsOut>(`/acquisitions/${acquisitionId}/proforma-inputs`),
  });
}

export function useSaveProformaInputs(acquisitionId: string) {
  // Persist the pro-forma assumptions; the server sizes debt + recomputes, so refresh the proforma.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProformaInputs) =>
      apiFetch<ProformaResults>(`/acquisitions/${acquisitionId}/proforma-inputs`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      // Saving inputs re-sizes debt + re-runs the promote server-side: refresh every derived view.
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "proforma"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "proforma-monthly"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "proforma-inputs"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "returns"] });
    },
  });
}

type WaterfallTier = Schemas["WaterfallTier"];
type WaterfallTiersUpdate = Schemas["WaterfallTiersUpdate"];

export function useWaterfallTiers(acquisitionId: string) {
  // The acquisition's persisted promote tiers (empty → the promote uses the configured defaults).
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "waterfall-tiers"],
    queryFn: () => apiFetch<WaterfallTier[]>(`/acquisitions/${acquisitionId}/waterfall-tiers`),
  });
}

export function useSaveWaterfallTiers(acquisitionId: string) {
  // Persist the promote hurdles/promotes; the headline returns then reflect them.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WaterfallTiersUpdate) =>
      apiFetch<WaterfallTier[]>(`/acquisitions/${acquisitionId}/waterfall-tiers`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "waterfall-tiers"] });
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "returns"] });
    },
  });
}

type BudgetDoc = Schemas["BudgetDoc"];
type BudgetCellUpdate = Schemas["BudgetCellUpdate"];

export function useBudget(acquisitionId: string) {
  // Prior-year-vs-year-one budget: prior actuals (computed) beside the editable year-one cells.
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "budget"],
    queryFn: () => apiFetch<BudgetDoc>(`/acquisitions/${acquisitionId}/budget`),
  });
}

export function useSeedBudget(acquisitionId: string) {
  // Prefill year-one from the mapped prior-year actuals (idempotent; never clobbers edits).
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<BudgetDoc>(`/acquisitions/${acquisitionId}/budget/seed`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "budget"] }),
  });
}

export function usePatchBudgetCell(acquisitionId: string) {
  // Edit one year-one cell → flips it to a human override.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BudgetCellUpdate) =>
      apiFetch<BudgetDoc>(`/acquisitions/${acquisitionId}/budget`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "budget"] }),
  });
}

export function useComps(acquisitionId: string) {
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "comps"],
    queryFn: () => apiFetch<CompSet>(`/acquisitions/${acquisitionId}/comps`),
  });
}

export function useMapping(acquisitionId: string) {
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "mapping"],
    queryFn: () => apiFetch<MappingReview>(`/acquisitions/${acquisitionId}/mapping`),
  });
}

type GlAccountOption = Schemas["GlAccountOption"];
type MappingConfirm = Schemas["MappingConfirm"];

export function useGlAccounts() {
  // The canonical GL chart (active accounts) for the mapping picker; cached app-wide.
  return useQuery({
    queryKey: ["gl-accounts"],
    queryFn: () => apiFetch<GlAccountOption[]>("/gl-accounts"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useConfirmMapping(acquisitionId: string) {
  // Human accepts a line's mapping (and optionally learns it); refresh the review queue.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MappingConfirm) =>
      apiFetch<MappingReview>(`/acquisitions/${acquisitionId}/mapping/confirm`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "mapping"] });
    },
  });
}

type MappingSplit = Schemas["MappingSplit"];

export function useSplitMapping(acquisitionId: string) {
  // Split one seller line across GLs (parts must sum to the line); refresh the review queue.
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MappingSplit) =>
      apiFetch<MappingReview>(`/acquisitions/${acquisitionId}/mapping/split`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["acquisition", acquisitionId, "mapping"] });
    },
  });
}

export function usePopulationRings(acquisitionId: string) {
  return useQuery({
    queryKey: ["acquisition", acquisitionId, "population-rings"],
    queryFn: () => apiFetch<PopulationRingsDoc>(`/acquisitions/${acquisitionId}/population-rings`),
  });
}

export function useGateQuestions(phase?: Phase) {
  const qs = phase ? `?phase=${phase}` : "";
  return useQuery({
    queryKey: ["gate-questions", phase ?? "all"],
    queryFn: () => apiFetch<GateQuestion[]>(`/gate-questions${qs}`),
  });
}

export function useFeedbackQueue(filters?: { status?: FeedbackStatus }) {
  const qs = filters?.status ? `?status=${filters.status}` : "";
  return useQuery({
    queryKey: ["feedback", filters ?? {}],
    queryFn: () => apiFetch<FeedbackOut[]>(`/feedback${qs}`),
  });
}

export function useSubmitFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FeedbackCreate) =>
      apiFetch<FeedbackOut>("/feedback", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
}

export function usePatchFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: FeedbackPatch }) =>
      apiFetch<FeedbackOut>(`/feedback/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
}

export function useDispatchFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DispatchRequest }) =>
      apiFetch<DispatchOut>(`/feedback/${id}/dispatch`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
}

export function useQuestionSuggestions(status?: SuggestionStatus) {
  const qs = status ? `?status=${status}` : "";
  return useQuery({
    queryKey: ["question-suggestions", status ?? "all"],
    queryFn: () => apiFetch<QuestionSuggestionOut[]>(`/question-suggestions${qs}`),
  });
}

export function useDecideSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: SuggestionStatus }) =>
      apiFetch<QuestionSuggestionOut>(`/question-suggestions/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["question-suggestions"] });
      qc.invalidateQueries({ queryKey: ["gate-questions"] });
    },
  });
}
