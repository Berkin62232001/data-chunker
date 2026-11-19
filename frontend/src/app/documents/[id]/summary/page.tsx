"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getDocumentSummary, type DocumentSummary } from "@/lib/api";

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{title}</p>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 text-xs">
      <span className="text-gray-400 w-40 shrink-0">{label}</span>
      <span className="text-gray-800 break-all">{value}</span>
    </div>
  );
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${color}`}>{label}</span>
  );
}

const PHASE_COLORS: Record<string, string> = {
  upload:           "bg-gray-100 text-gray-600",
  profiled:         "bg-blue-100 text-blue-700",
  pipeline_decided: "bg-indigo-100 text-indigo-700",
  converted:        "bg-amber-100 text-amber-700",
  chunked:          "bg-green-100 text-green-700",
};

const STATUS_COLORS: Record<string, string> = {
  raw:     "bg-gray-100 text-gray-600",
  success: "bg-green-100 text-green-700",
  partial: "bg-yellow-100 text-yellow-700",
  failed:  "bg-red-100 text-red-700",
};

const INTEG_COLORS: Record<string, string> = {
  pass: "bg-green-100 text-green-700",
  warn: "bg-yellow-100 text-yellow-700",
  fail: "bg-red-100 text-red-700",
};

export default function DocumentSummaryPage() {
  const params = useParams<{ id: string }>();
  const documentId = params.id;

  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId) return;
    getDocumentSummary(documentId)
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load summary"));
  }, [documentId]);

  if (error) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-10">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      </main>
    );
  }

  if (!summary) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-10">
        <p className="text-sm text-gray-400 animate-pulse">Loading summary…</p>
      </main>
    );
  }

  return (
    <main className="max-w-2xl mx-auto px-6 py-8 space-y-4">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-xs text-gray-400">
        <Link href="/" className="hover:text-gray-700">Dashboard</Link>
        <span>/</span>
        <Link href="/documents" className="hover:text-gray-700">Documents</Link>
        <span>/</span>
        <Link href={`/documents/${documentId}`} className="hover:text-gray-700 truncate max-w-xs">
          {summary.original_filename}
        </Link>
        <span>/</span>
        <span className="text-gray-700">Summary</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{summary.original_filename}</h1>
          <p className="text-xs font-mono text-gray-400 mt-0.5">{summary.document_id}</p>
        </div>
        <span className="shrink-0 px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-500">
          Read-only summary
        </span>
      </div>

      {/* Overview */}
      <Section title="Overview">
        <Row label="Status" value={
          <Badge label={summary.status} color={STATUS_COLORS[summary.status] ?? "bg-gray-100 text-gray-600"} />
        } />
        <Row label="Phase" value={
          <Badge label={summary.current_phase} color={PHASE_COLORS[summary.current_phase] ?? "bg-gray-100 text-gray-600"} />
        } />
        <Row label="File size" value={formatBytes(summary.file_size_bytes)} />
        {summary.mime_type && (
          <Row label="MIME type" value={<span className="font-mono">{summary.mime_type}</span>} />
        )}
        <Row label="Uploaded" value={formatDate(summary.created_at)} />
      </Section>

      {/* Profile summary */}
      {summary.profile && (
        <Section title="Profile">
          {summary.profile.detected_type && (
            <Row label="Detected type" value={summary.profile.detected_type} />
          )}
          {summary.profile.page_count != null && (
            <Row label="Pages" value={String(summary.profile.page_count)} />
          )}
          <Row label="Requires OCR" value={summary.profile.requires_ocr ? "Yes" : "No"} />
        </Section>
      )}

      {/* Pipeline summary */}
      {summary.pipeline && (
        <Section title="Pipeline">
          <Row
            label="Selected pipeline"
            value={<span className="font-semibold text-indigo-700">{summary.pipeline.selected_pipeline}</span>}
          />
          {summary.pipeline.output_format && (
            <Row label="Output format" value={<span className="font-mono">{summary.pipeline.output_format}</span>} />
          )}
        </Section>
      )}

      {/* Conversion summary */}
      {summary.conversion && (
        <Section title="Conversion">
          <Row
            label="Status"
            value={<Badge label={summary.conversion.status} color={STATUS_COLORS[summary.conversion.status] ?? "bg-gray-100 text-gray-600"} />}
          />
          {summary.conversion.converter_used && (
            <Row label="Converter" value={<span className="font-mono">{summary.conversion.converter_used}</span>} />
          )}
          {summary.conversion.estimated_tokens != null && (
            <Row label="Est. tokens" value={`~${summary.conversion.estimated_tokens.toLocaleString()}`} />
          )}
        </Section>
      )}

      {/* Chunks summary */}
      {summary.chunks && (
        <Section title="Chunks">
          <Row label="Total chunks" value={summary.chunks.total_chunks.toLocaleString()} />
          {summary.chunks.total_estimated_tokens != null && (
            <Row label="Est. tokens" value={`~${summary.chunks.total_estimated_tokens.toLocaleString()}`} />
          )}
          {summary.chunks.chunking_strategy && (
            <Row label="Strategy" value={<span className="font-mono">{summary.chunks.chunking_strategy}</span>} />
          )}
        </Section>
      )}

      {/* Integrity + security */}
      {(summary.integrity_status || summary.security_warnings_count != null) && (
        <Section title="Quality">
          {summary.integrity_status && (
            <Row
              label="Integrity"
              value={<Badge label={summary.integrity_status} color={INTEG_COLORS[summary.integrity_status] ?? "bg-gray-100 text-gray-600"} />}
            />
          )}
          {summary.security_warnings_count != null && (
            <Row
              label="Injection warnings"
              value={
                summary.security_warnings_count === 0 ? (
                  <span className="text-green-600">None detected</span>
                ) : (
                  <span className="text-amber-600">{summary.security_warnings_count} warning{summary.security_warnings_count !== 1 ? "s" : ""}</span>
                )
              }
            />
          )}
        </Section>
      )}

      {/* Preview excerpt */}
      {summary.preview_excerpt && (
        <Section title="Content Preview">
          <pre className="overflow-auto rounded-lg bg-gray-950 text-gray-100 text-xs p-3 leading-relaxed whitespace-pre-wrap break-words max-h-72">
            {summary.preview_excerpt}
          </pre>
          <p className="text-xs text-gray-400">
            Showing first {summary.preview_excerpt.length.toLocaleString()} characters.
          </p>
        </Section>
      )}

      {/* Back button */}
      <div className="pt-2">
        <a
          href={`/documents/${documentId}`}
          className="inline-flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 font-medium"
        >
          ← Back to document
        </a>
      </div>
    </main>
  );
}
