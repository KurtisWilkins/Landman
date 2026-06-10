/**
 * Minimal typed fetch wrapper.
 *
 * Server state lives in TanStack Query + the server (CLAUDE.md): this client holds NO
 * app state and uses NO browser storage. The base URL comes from the build-time env; in
 * dev, Vite proxies `/api` to the backend.
 */
import { addBreadcrumb, setLastApiError } from "../lib/telemetry";
import type { components, paths } from "./types";

export type Schemas = components["schemas"];
export type Paths = paths;

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

// Dev-only auth shim until Entra OIDC lands (decision C-16); never a real credential.
const DEV_BEARER = import.meta.env.VITE_DEV_BEARER as string | undefined;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? "GET";
  addBreadcrumb("api", `${method} ${path}`);
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(DEV_BEARER ? { Authorization: `Bearer ${DEV_BEARER}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let code = "error";
    let message = res.statusText;
    let detail: unknown;
    try {
      const body = (await res.json()) as {
        error?: { code: string; message: string; detail?: unknown };
      };
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
        detail = body.error.detail;
      }
    } catch {
      /* non-JSON error body */
    }
    // Feed the bug-report path: keep the last API error in memory (no browser storage).
    setLastApiError({ status: res.status, code, message, path, method });
    throw new ApiError(res.status, code, message, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
