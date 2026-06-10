/**
 * In-memory client telemetry that feeds the bug-report path (design doc §5.10, §7).
 *
 * NO browser storage (CLAUDE.md): breadcrumbs, captured console errors, and the last API
 * error live in module-scoped ring buffers for the session only. The same breadcrumb buffer
 * that powers Sentry is what the feedback widget attaches to a bug report.
 */

export interface Breadcrumb {
  ts: string;
  category: string;
  message: string;
  data?: Record<string, unknown>;
}

const MAX_BREADCRUMBS = 50;
const MAX_CONSOLE_ERRORS = 20;

const breadcrumbs: Breadcrumb[] = [];
const consoleErrors: Array<Record<string, unknown>> = [];
let lastApiError: Record<string, unknown> | null = null;

export function addBreadcrumb(
  category: string,
  message: string,
  data?: Record<string, unknown>,
): void {
  breadcrumbs.push({ ts: new Date().toISOString(), category, message, data });
  if (breadcrumbs.length > MAX_BREADCRUMBS) breadcrumbs.shift();
}

export function getBreadcrumbs(): Breadcrumb[] {
  return [...breadcrumbs];
}

export function recordConsoleError(message: string, data?: Record<string, unknown>): void {
  consoleErrors.push({ ts: new Date().toISOString(), message, ...data });
  if (consoleErrors.length > MAX_CONSOLE_ERRORS) consoleErrors.shift();
}

export function getConsoleErrors(): Array<Record<string, unknown>> {
  return [...consoleErrors];
}

export function setLastApiError(error: Record<string, unknown> | null): void {
  lastApiError = error;
}

export function getLastApiError(): Record<string, unknown> | null {
  return lastApiError;
}

let consoleInstalled = false;

/** Wrap console.error so client errors are captured for bug reports. Idempotent. */
export function installConsoleCapture(): void {
  if (consoleInstalled || typeof console === "undefined") return;
  consoleInstalled = true;
  const original = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    recordConsoleError(args.map((a) => (a instanceof Error ? a.message : String(a))).join(" "));
    addBreadcrumb("console", "console.error");
    original(...args);
  };
}

/** Test helper: reset all buffers. */
export function _resetTelemetry(): void {
  breadcrumbs.length = 0;
  consoleErrors.length = 0;
  lastApiError = null;
}
