/** Number formatting for financial figures. Decimals arrive from the API as strings.
 * Currency $#,##0 with negatives in parentheses; percentages 0.0%; multiples 0.00x. */

type Num = string | number | null | undefined;

export function fmtUsd(v: Num): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  const s = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Math.abs(n));
  return n < 0 ? `(${s})` : s;
}

const PCT = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function fmtPct(v: Num): string {
  if (v == null || v === "") return "—";
  return PCT.format(Number(v)); // Intl rounds half-up correctly (avoids ×100 float drift)
}

export function fmtMult(v: Num): string {
  if (v == null || v === "") return "—";
  return `${Number(v).toFixed(2)}x`;
}
