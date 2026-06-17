/**
 * Typed server-state hooks (TanStack Query) against the generated §9 contract.
 * Data-fetching lives here; components stay presentational (CLAUDE.md).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "./types";
import { apiFetch, apiUpload, type Schemas } from "./client";

type DealSummary = Schemas["DealSummary"];
type DealDocument = Schemas["DealDocument"];
type DealCreate = Schemas["DealCreate"];
/** Result of POST /deals/{id}/documents (endpoint returns an untyped dict, so typed here). */
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
    queryKey: ["deals", filters ?? {}],
    queryFn: () => apiFetch<DealSummary[]>(`/deals${qs}`),
  });
}

export function useCreateDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: DealCreate) =>
      apiFetch<DealDocument>("/deals", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deals"] }),
  });
}

type OmProposal = Schemas["OmProposal"];

export function useExtractOm() {
  // Extracts a reviewable proposal from an OM PDF (nothing is persisted server-side).
  return useMutation({
    mutationFn: (file: File) => apiUpload<OmProposal>("/deals/extract-om", file),
  });
}

export function useUploadDocument(dealId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUpload<UploadResult>(`/deals/${dealId}/documents`, file),
    onSuccess: () => {
      // The upload changes the deal's financials + mapping queue; refresh both.
      qc.invalidateQueries({ queryKey: ["deal", dealId] });
      qc.invalidateQueries({ queryKey: ["deal", dealId, "mapping"] });
    },
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

export function useDeal(dealId: string) {
  return useQuery({
    queryKey: ["deal", dealId],
    queryFn: () => apiFetch<DealDocument>(`/deals/${dealId}`),
  });
}

export function useProforma(dealId: string) {
  return useQuery({
    queryKey: ["deal", dealId, "proforma"],
    queryFn: () => apiFetch<ProformaResults>(`/deals/${dealId}/proforma`),
  });
}

export function useComps(dealId: string) {
  return useQuery({
    queryKey: ["deal", dealId, "comps"],
    queryFn: () => apiFetch<CompSet>(`/deals/${dealId}/comps`),
  });
}

export function useMapping(dealId: string) {
  return useQuery({
    queryKey: ["deal", dealId, "mapping"],
    queryFn: () => apiFetch<MappingReview>(`/deals/${dealId}/mapping`),
  });
}

export function usePopulationRings(dealId: string) {
  return useQuery({
    queryKey: ["deal", dealId, "population-rings"],
    queryFn: () => apiFetch<PopulationRingsDoc>(`/deals/${dealId}/population-rings`),
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
