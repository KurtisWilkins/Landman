/**
 * Source-document upload (design doc §5.2): pick an Excel/CSV (or PDF once extraction is
 * configured), POST it, and show the normalized-load result. Seller files are untrusted and
 * size-limited server-side. Presentational — the upload lives in the useUploadDocument hook.
 */
import { useRef, useState } from "react";
import { useUploadDocument, type UploadResult } from "../../api/hooks";
import { ApiError } from "../../api/client";

export function DocUpload({ dealId }: { dealId: string }) {
  const upload = useUploadDocument(dealId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  function submit() {
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (r) => {
        setResult(r);
        setFile(null);
        if (inputRef.current) inputRef.current.value = "";
      },
    });
  }

  return (
    <div className="rounded-lg border border-forest/15 p-4">
      <div className="text-sm font-medium">Upload a source document</div>
      <p className="mt-1 text-xs opacity-70">
        Excel or CSV (P&amp;L, unit mix, rent roll). PDF extraction activates once the AI provider
        is configured.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          aria-label="Source document"
          accept=".csv,.xlsx,.xls,.pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        <button
          onClick={submit}
          disabled={!file || upload.isPending}
          className="rounded bg-forest px-3 py-1.5 text-sm text-bone disabled:opacity-50"
        >
          {upload.isPending ? "Uploading…" : "Upload"}
        </button>
      </div>

      {upload.isError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {upload.error instanceof ApiError ? upload.error.message : "Upload failed."}
        </p>
      )}

      {result && (
        <p className="mt-3 text-sm">
          Loaded <span className="font-medium">{result.sheet_type}</span> —{" "}
          <span className="font-figure">{result.financial_lines_loaded}</span> financial lines,{" "}
          <span className="font-figure">{result.units_loaded}</span> unit rows.
        </p>
      )}
    </div>
  );
}
