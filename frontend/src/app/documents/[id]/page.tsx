"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  askGroundedAnswer,
  cancelJob,
  chunkDocument,
  convertDocument,
  createChunkJob,
  createConvertJob,
  createGroundedAnswerJob,
  createIndexJob,
  createRetrievalEvaluationJob,
  estimateContext,
  evaluateRetrieval,
  evaluateRetrievalSet,
  exportArtifact,
  fetchChunkQuality,
  fetchDocumentIndexStatus,
  fetchDocumentPreview,
  fetchHealth,
  fetchIntegrity,
  fetchJob,
  fetchPipeline,
  fetchProfile,
  fetchTokenEfficiency,
  getChunks,
  getConverted,
  getDocumentAudit,
  getDocumentDetail,
  hybridSearchDocument,
  indexDocument,
  initializeDocument,
  listDocumentJobs,
  prepareLlmPayload,
  retryJob,
  searchDocument,
  semanticSearchDocument,
  type AuditEventItem,
  type ChunkingResult,
  type ChunkQualityReport,
  type ChunkPreview,
  type ConversionResult,
  type DocumentDetail,
  type DocumentIndexStatusResponse,
  type DocumentPreview,
  type DocumentProfile,
  type EstimateContextResponse,
  type ExportArtifact,
  type GatewayProvider,
  type GroundedAnswerResponse,
  type HybridResultItem,
  type HybridSearchResponse,
  type IndexResponse,
  type IntegrityReport,
  type JobDetail,
  type LLMPayloadResponse,
  type LLMProvider,
  type PipelineDecision,
  type RetrievalEvaluationResponse,
  type RetrievalEvaluationSetResponse,
  type RetrievalMode,
  type SearchResponse,
  type SemanticSearchResponse,
  type TokenEfficiencySummary,
} from "@/lib/api";
import { SecurityPanel } from "@/components/SecurityPanel";
import { ProjectPanel } from "@/components/ProjectPanel";

// ── Types ─────────────────────────────────────────────────────────────────────

type AsyncState = "idle" | "loading" | "success" | "error";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

function formatMaybeBool(value: boolean | null | undefined): string {
  if (value == null) return "Unknown";
  return value ? "Yes" : "No";
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toFixed(1)}%`;
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function Spinner({ className = "" }: { className?: string }) {
  return <div className={`border-2 border-t-transparent rounded-full animate-spin ${className}`} />;
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap border border-transparent ${color}`}>
      {label}
    </span>
  );
}

function Card({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-[var(--radius)] overflow-hidden"
      style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--card-shadow)" }}
    >
      {(title || badge) && (
        <div
          className="flex items-center justify-between gap-3 px-4 py-3"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <p
            className="text-[11px] font-semibold uppercase tracking-[0.06em]"
            style={{ color: "var(--text-2)" }}
          >
            {title}
          </p>
          {badge && <div className="flex items-center gap-1.5 shrink-0">{badge}</div>}
        </div>
      )}
      <div className="p-4 space-y-3">
        {children}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      className="flex items-start gap-3 text-xs py-1.5"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      <span className="w-36 shrink-0" style={{ color: "var(--text-3)" }}>{label}</span>
      <span className="flex-1 text-right break-all" style={{ color: "var(--text)" }}>{value}</span>
    </div>
  );
}

function ActionButton({
  onClick,
  loading,
  disabled,
  label,
  loadingLabel,
  variant = "primary",
}: {
  onClick: () => void;
  loading: boolean;
  disabled?: boolean;
  label: string;
  loadingLabel: string;
  variant?: "primary" | "secondary" | "danger";
}) {
  const base = "w-full py-2.5 rounded-[var(--radius-xs)] text-sm font-semibold transition-all flex items-center justify-center gap-2";
  if (loading || disabled) {
    return (
      <button disabled className={`${base} cursor-default`} style={{ background: "var(--surface-3)", color: "var(--text-3)" }}>
        {loading ? <><Spinner className="w-4 h-4 border-current opacity-50" />{loadingLabel}</> : label}
      </button>
    );
  }
  if (variant === "primary") {
    return (
      <button onClick={onClick} className={`${base} btn-grad`}>
        {label}
      </button>
    );
  }
  if (variant === "danger") {
    return (
      <button onClick={onClick} className={`${base}`} style={{ background: "#dc4436", color: "#fff" }}>
        {label}
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className={`${base}`}
      style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border-2)" }}
    >
      {label}
    </button>
  );
}

const TERMINAL_JOB_STATUSES = ["succeeded", "failed", "canceled"];

function isTerminalJob(job: JobDetail | null): boolean {
  return job != null && TERMINAL_JOB_STATUSES.includes(job.status);
}

function useJobPolling(
  job: JobDetail | null,
  setJob: (job: JobDetail | null) => void,
  onSucceeded?: (job: JobDetail) => void | Promise<void>,
) {
  const jobId = job?.job_id;
  const jobStatus = job?.status;
  useEffect(() => {
    if (!jobId || !jobStatus || TERMINAL_JOB_STATUSES.includes(jobStatus)) return;
    let stopped = false;
    const poll = async () => {
      try {
        const updated = await fetchJob(jobId);
        if (stopped) return;
        setJob(updated);
        if (updated.status === "succeeded") {
          await onSucceeded?.(updated);
        }
      } catch {
        // Keep the last known job state visible; the next poll may recover.
      }
    };
    const timer = window.setInterval(poll, 1500);
    poll();
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [jobId, jobStatus, setJob, onSucceeded]);
}

function JobProgress({ job, onCancel }: { job: JobDetail | null; onCancel: () => void }) {
  if (!job) return null;
  const running = job.status === "queued" || job.status === "running";
  const barColor = job.status === "succeeded"
    ? "#16a35a"
    : job.status === "failed"
    ? "#dc4436"
    : job.status === "canceled"
    ? "var(--text-3)"
    : "linear-gradient(90deg, #7a4ff7, #3f6bf6)";

  return (
    <div
      className="rounded-[var(--radius-sm)] px-3.5 py-3 space-y-2"
      style={{ background: "var(--inset)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold capitalize" style={{ color: "var(--text)" }}>{job.status}</p>
          <p className="text-xs truncate mt-0.5" style={{ color: "var(--text-3)" }}>
            {job.message ?? job.current_step ?? job.job_type}
          </p>
        </div>
        {running && (
          <button onClick={onCancel} className="shrink-0 text-xs font-medium" style={{ color: "var(--text-3)", background: "none", border: "none", cursor: "pointer" }}>
            Cancel
          </button>
        )}
      </div>
      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.min(100, Math.max(0, job.progress_percent))}%`, background: barColor }}
        />
      </div>
      <div className="flex justify-between text-[11px]" style={{ color: "var(--text-3)" }}>
        <span>{job.current_step ?? job.job_type}</span>
        <span>{job.progress_percent}%</span>
      </div>
      {job.error && <p className="text-xs" style={{ color: "#c2382b" }}>{job.error}</p>}
    </div>
  );
}

// ── Pipeline tracker ──────────────────────────────────────────────────────────

const STEPS = [
  { key: "upload",           label: "Upload" },
  { key: "profiled",         label: "Profile" },
  { key: "pipeline_decided", label: "Pipeline" },
  { key: "converted",        label: "Convert" },
  { key: "chunked",          label: "Chunk" },
];

function PipelineTracker({ currentPhase, activeStep }: { currentPhase: string; activeStep?: string }) {
  const idx = STEPS.findIndex((s) => s.key === currentPhase);
  const stepIcons: Record<string, string> = {
    upload:           '<path d="M12 16V4m0 0l-4 4m4-4l4 4"/><path d="M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2"/>',
    profiled:         '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.2-3.2"/>',
    pipeline_decided: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="8" r="2.5"/><path d="M6 8.5v7M8.5 8h4a3 3 0 013 3v0"/>',
    converted:        '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
    chunked:          '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  };
  const checkPath = '<path d="M5 12.5l4.5 4.5L19 6.5"/>';
  return (
    <div className="flex items-center w-full overflow-x-auto pb-1 gap-0">
      {STEPS.map((step, i) => {
        const done = i <= idx;
        const running = step.key === activeStep;
        const isCurrent = i === idx && !running;
        return (
          <div key={step.key} className="flex items-center flex-1 min-w-0">
            <div className="flex flex-col items-center gap-2 shrink-0">
              <div className={`pt-node ${done ? "done" : ""} ${running ? "running" : ""} ${isCurrent && !done ? "current" : ""}`}>
                {running ? (
                  <Spinner className="w-4 h-4 border-white" />
                ) : done ? (
                  <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" dangerouslySetInnerHTML={{ __html: checkPath }} />
                ) : (
                  <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" dangerouslySetInnerHTML={{ __html: stepIcons[step.key] ?? "" }} />
                )}
              </div>
              <span
                className="text-[11px] font-medium whitespace-nowrap"
                style={{ color: done || running ? "var(--text)" : "var(--text-3)", fontWeight: (isCurrent || running) ? 650 : 500 }}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className="flex-1 h-0.5 mx-1.5 mb-5 rounded"
                style={{ background: i < idx ? "linear-gradient(90deg, #7a4ff7, #3f6bf6)" : "var(--border-2)" }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Profile panel ─────────────────────────────────────────────────────────────

const CAT_COLORS: Record<string, string> = {
  pdf:      "bg-red-100 text-red-700",
  docx:     "bg-blue-100 text-blue-700",
  pptx:     "bg-orange-100 text-orange-700",
  xlsx:     "bg-green-100 text-green-700",
  csv:      "bg-emerald-100 text-emerald-700",
  txt:      "bg-gray-100 text-gray-700",
  markdown: "bg-gray-100 text-gray-700",
  html:     "bg-amber-100 text-amber-700",
  image:    "bg-purple-100 text-purple-700",
  unknown:  "bg-gray-100 text-gray-500",
};

function ProfileCard({ profile }: { profile: DocumentProfile }) {
  return (
    <Card
      title="Document Profile"
      badge={<Badge label={profile.category} color={CAT_COLORS[profile.category] ?? CAT_COLORS.unknown} />}
    >
      <Row label="Detected type" value={profile.content_type ?? profile.category} />
      {profile.page_count != null && <Row label="Pages" value={String(profile.page_count)} />}
      <Row label="Text layer" value={formatMaybeBool(profile.has_text_layer)} />
      <Row label="OCR needed" value={profile.requires_ocr ? "Yes" : "No"} />
      <Row label="Scanned-like" value={formatMaybeBool(profile.scanned_like)} />
      {profile.extracted_text_char_count != null && (
        <Row label="Extracted chars" value={profile.extracted_text_char_count.toLocaleString()} />
      )}
      {profile.mime_type && <Row label="MIME" value={<span className="font-mono">{profile.mime_type}</span>} />}
      <Row label="Pipeline recommendation" value={profile.recommended_pipeline} />
      {profile.requires_ocr && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-xs text-amber-700">
            This document appears scanned or image-heavy. Enable OCR to extract text.
          </p>
          {profile.ocr_reason && <p className="mt-1 text-xs text-amber-700">{profile.ocr_reason}</p>}
        </div>
      )}
    </Card>
  );
}

// ── Pipeline decision card ────────────────────────────────────────────────────

const PIPE_LABELS: Record<string, string> = {
  ocr_pdf_to_markdown_jsonl:              "OCR → Markdown JSONL",
  standard_pdf_to_markdown_jsonl:         "PDF → Markdown JSONL",
  advanced_pdf_docling_to_markdown_jsonl: "Docling PDF → Markdown JSONL",
  docx_to_markdown_jsonl:                 "DOCX → Markdown JSONL",
  pptx_to_slide_markdown_jsonl:           "PPTX → Slide JSONL",
  tabular_to_structured_json_summary:     "Tabular → Structured JSON",
  text_to_markdown_jsonl:                 "Text → Markdown JSONL",
  html_to_clean_markdown_jsonl:           "HTML → Markdown JSONL",
  image_ocr_to_markdown_jsonl:            "Image OCR → Markdown JSONL",
  fallback_text_extraction:               "Fallback Text Extraction",
};

function PipelineCard({ decision }: { decision: PipelineDecision }) {
  const label = PIPE_LABELS[decision.selected_pipeline] ?? decision.selected_pipeline;
  return (
    <Card title="Pipeline Decision">
      <Row label="Selected pipeline" value={<span className="font-semibold text-indigo-700">{label}</span>} />
      <Row label="Output format" value={<span className="font-mono">{decision.output_format}</span>} />
      <Row label="LLM format (Claude)" value={<span className="font-mono">{decision.llm_send_format_claude}</span>} />
      {decision.reasons.length > 0 && (
        <div>
          <p className="text-xs text-gray-400 mb-1">Reasons</p>
          <ul className="space-y-0.5">
            {decision.reasons.map((r, i) => (
              <li key={i} className="flex gap-2 text-xs text-gray-600">
                <span className="text-indigo-400 shrink-0">›</span>{r}
              </li>
            ))}
          </ul>
        </div>
      )}
      {decision.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {decision.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-700">⚠ {w}</p>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Conversion card ───────────────────────────────────────────────────────────

const CONV_BADGE: Record<string, string> = {
  success: "bg-green-100 text-green-700",
  partial: "bg-yellow-100 text-yellow-700",
  failed:  "bg-red-100 text-red-700",
};

function ConversionCard({ conversion }: { conversion: ConversionResult }) {
  const [showPreview, setShowPreview] = useState(false);
  const { report, metadata, markdown_preview } = conversion;
  return (
    <Card
      title="Conversion"
      badge={<Badge label={conversion.conversion_status} color={CONV_BADGE[conversion.conversion_status] ?? "bg-gray-100 text-gray-600"} />}
    >
      <Row label="Converter" value={<span className="font-mono">{report.converter_used}</span>} />
      <Row label="Fallback used" value={report.fallback_used ? "Yes" : "No"} />
      <Row label="Characters" value={metadata.estimated_character_count.toLocaleString()} />
      <Row label="Est. tokens" value={`~${metadata.estimated_token_count.toLocaleString()}`} />
      {report.ocr_succeeded != null && (
        <div className="space-y-1 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
          <Row label="OCR used" value={report.ocr_used ? "Yes" : "No"} />
          {report.ocr_provider && <Row label="OCR provider" value={<span className="font-mono">{report.ocr_provider}</span>} />}
          {report.ocr_language && <Row label="OCR language" value={<span className="font-mono">{report.ocr_language}</span>} />}
          {report.ocr_pages_processed != null && <Row label="OCR pages" value={String(report.ocr_pages_processed)} />}
          <Row label="OCR chars" value={report.ocr_text_char_count.toLocaleString()} />
        </div>
      )}
      {report.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {report.warnings.map((w, i) => <p key={i} className="text-xs text-amber-700">⚠ {w}</p>)}
        </div>
      )}
      {report.ocr_warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {report.ocr_warnings.map((w, i) => <p key={i} className="text-xs text-amber-700">⚠ {w}</p>)}
        </div>
      )}
      {report.ocr_error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2">
          <p className="text-xs text-red-700">{report.ocr_error}</p>
        </div>
      )}
      {markdown_preview && (
        <div>
          <button
            onClick={() => setShowPreview((v) => !v)}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
          >
            {showPreview ? "Hide" : "Show"} document preview
          </button>
          {showPreview && (
            <pre className="mt-2 overflow-auto max-h-48 rounded-lg bg-gray-950 text-gray-100 text-xs p-3 leading-relaxed whitespace-pre-wrap break-words">
              {markdown_preview}
            </pre>
          )}
        </div>
      )}
    </Card>
  );
}

// ── Chunks card ───────────────────────────────────────────────────────────────

const CT_COLORS: Record<string, string> = {
  text:  "bg-gray-100 text-gray-600",
  code:  "bg-violet-100 text-violet-700",
  table: "bg-teal-100 text-teal-700",
};

function ChunksCard({ data }: { data: ChunkingResult }) {
  const { manifest, chunks_preview } = data;
  const [expanded, setExpanded] = useState(false);
  return (
    <Card title="Chunks">
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Total chunks", value: manifest.total_chunks.toLocaleString() },
          { label: "Est. tokens",  value: manifest.total_estimated_tokens.toLocaleString() },
          { label: "Avg tokens",   value: manifest.average_chunk_tokens.toLocaleString() },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border border-gray-100 bg-gray-50 p-2.5 text-center">
            <p className="text-base font-bold text-gray-900">{value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{label}</p>
          </div>
        ))}
      </div>
      <Row label="Strategy" value={<span className="font-mono">{manifest.chunking_strategy}</span>} />
      {chunks_preview.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
          >
            {expanded ? "Hide" : "Show"} chunk preview ({chunks_preview.length})
          </button>
          {expanded && (
            <div className="mt-2 space-y-1.5">
              {chunks_preview.map((chunk: ChunkPreview) => {
                const ctColor = CT_COLORS[chunk.content_type] ?? CT_COLORS.text;
                const bc = chunk.section_path.join(" › ") || "(root)";
                return (
                  <div key={chunk.chunk_id} className="rounded-lg border border-gray-100 p-2.5 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-gray-400 truncate">{bc}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Badge label={chunk.content_type} color={ctColor} />
                        <span className="text-xs text-gray-400">~{chunk.estimated_tokens}t</span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap line-clamp-2">
                      {chunk.text_preview}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// ── Integrity panel ───────────────────────────────────────────────────────────

const CHECK_ICONS: Record<string, string> = { pass: "✓", warn: "⚠", fail: "✕", skip: "○" };
const CHECK_COLORS: Record<string, string> = {
  pass: "text-green-600", warn: "text-amber-500", fail: "text-red-600", skip: "text-gray-400",
};
const INTEG_BADGE: Record<string, string> = {
  pass: "bg-green-100 text-green-700", warn: "bg-yellow-100 text-yellow-700", fail: "bg-red-100 text-red-700",
};

function IntegrityCard({ report }: { report: IntegrityReport }) {
  return (
    <Card title="Integrity" badge={<Badge label={report.status} color={INTEG_BADGE[report.status] ?? "bg-gray-100 text-gray-600"} />}>
      <ul className="space-y-1">
        {report.checks.map((c) => (
          <li key={c.name} className="flex gap-2 text-xs">
            <span className={`shrink-0 font-bold w-3 ${CHECK_COLORS[c.status]}`}>{CHECK_ICONS[c.status]}</span>
            <span className="text-gray-400 w-32 shrink-0 truncate">{c.name}</span>
            <span className="text-gray-700">{c.message}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ── Export panel ──────────────────────────────────────────────────────────────

const EXPORT_ITEMS: {
  key: ExportArtifact;
  label: string;
  ext: string;
  requiresConversion?: boolean;
  requiresChunks?: boolean;
  requiresProfile?: boolean;
  requiresPipeline?: boolean;
}[] = [
  { key: "markdown",  label: "Markdown",          ext: ".md",    requiresConversion: true },
  { key: "chunks",    label: "Chunks JSONL",       ext: ".jsonl", requiresChunks: true },
  { key: "metadata",  label: "Metadata JSON",      ext: ".json",  requiresConversion: true },
  { key: "profile",   label: "Profile JSON",       ext: ".json",  requiresProfile: true },
  { key: "pipeline",  label: "Pipeline JSON",      ext: ".json",  requiresPipeline: true },
  { key: "integrity", label: "Integrity Report",   ext: ".json" },
];

function ExportPanel({
  documentId,
  hasProfile,
  hasPipeline,
  hasConversion,
  hasChunks,
}: {
  documentId: string;
  hasProfile: boolean;
  hasPipeline: boolean;
  hasConversion: boolean;
  hasChunks: boolean;
}) {
  const [downloading, setDownloading] = useState<ExportArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async (artifact: ExportArtifact) => {
    setDownloading(artifact);
    setError(null);
    try {
      await exportArtifact(documentId, artifact);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  };

  const isAvailable = (item: (typeof EXPORT_ITEMS)[number]) => {
    if (item.requiresConversion && !hasConversion) return false;
    if (item.requiresChunks && !hasChunks) return false;
    if (item.requiresProfile && !hasProfile) return false;
    if (item.requiresPipeline && !hasPipeline) return false;
    return true;
  };

  return (
    <Card title="Export Artifacts">
      <div className="grid grid-cols-2 gap-2">
        {EXPORT_ITEMS.map((item) => {
          const available = isAvailable(item);
          const busy = downloading === item.key;
          return (
            <button
              key={item.key}
              onClick={() => available && handleExport(item.key)}
              disabled={!available || downloading !== null}
              title={available ? `Download ${item.label}` : "Complete the required pipeline step first"}
              className={[
                "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors text-left",
                !available
                  ? "border-gray-100 bg-gray-50 text-gray-300 cursor-not-allowed"
                  : busy
                  ? "border-indigo-200 bg-indigo-50 text-indigo-500 cursor-default"
                  : "border-gray-200 bg-white text-gray-700 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50",
              ].join(" ")}
            >
              {busy ? (
                <Spinner className="w-3 h-3 border-indigo-400 shrink-0" />
              ) : (
                <span className="text-gray-400 shrink-0">↓</span>
              )}
              <span className="truncate">{item.label}</span>
              <span className="text-gray-300 shrink-0 ml-auto font-mono">{item.ext}</span>
            </button>
          );
        })}
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex justify-end">
        <a
          href={`/documents/${documentId}/summary`}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
        >
          View read-only summary →
        </a>
      </div>
    </Card>
  );
}

function QdrantBadge({ configured, available }: { configured: boolean; available: boolean }) {
  if (!configured) {
    return <Badge label="Qdrant not configured" color="bg-gray-100 text-gray-500" />;
  }
  if (!available) {
    return <Badge label="Qdrant unavailable" color="bg-red-100 text-red-700" />;
  }
  return <Badge label="Qdrant connected" color="bg-green-100 text-green-700" />;
}

function IndexPanel({ documentId, isIndexed, onIndexed }: { documentId: string; isIndexed: boolean; onIndexed: (indexed: boolean) => void }) {
  const [state, setState] = useState<AsyncState>("idle");
  const [index, setIndex] = useState<IndexResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [indexStatus, setIndexStatus] = useState<DocumentIndexStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [indexJob, setIndexJob] = useState<JobDetail | null>(null);

  // Load index status on mount
  useEffect(() => {
    fetchDocumentIndexStatus(documentId)
      .then((data) => {
        setIndexStatus(data);
        if (data.indexed) onIndexed(true);
      })
      .catch(() => {})
      .finally(() => setStatusLoading(false));
  }, [documentId, onIndexed]);

  const refreshStatus = useCallback(async () => {
    try {
      const data = await fetchDocumentIndexStatus(documentId);
      setIndexStatus(data);
      onIndexed(data.indexed);
    } catch { /* ignore */ }
  }, [documentId, onIndexed]);

  const handleIndex = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const data = await indexDocument(documentId);
      setIndex(data);
      setState("success");
      onIndexed(true);
      await refreshStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Indexing failed");
      setState("error");
    }
  }, [documentId, onIndexed, refreshStatus]);

  const handleIndexJob = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const job = await createIndexJob(documentId);
      setIndexJob(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Index job failed to start");
      setState("error");
    }
  }, [documentId]);

  const handleIndexJobSucceeded = useCallback(async () => {
    setState("success");
    onIndexed(true);
    await refreshStatus();
  }, [onIndexed, refreshStatus]);

  useJobPolling(indexJob, setIndexJob, handleIndexJobSucceeded);

  const handleCancelIndexJob = useCallback(async () => {
    if (!indexJob) return;
    try {
      setIndexJob(await cancelJob(indexJob.job_id));
      setState("idle");
    } catch { /* ignore */ }
  }, [indexJob]);

  const qdrantConfigured = indexStatus?.qdrant_configured ?? false;
  const qdrantAvailable = indexStatus?.qdrant_available ?? false;
  const indexed = indexStatus?.indexed ?? isIndexed;
  const indexedChunks = indexStatus?.indexed_chunks ?? 0;
  const embeddingProvider = indexStatus?.embedding_provider ?? index?.embedding_provider;
  const embeddingModel = indexStatus?.embedding_model ?? index?.embedding_model;
  const vectorSize = indexStatus?.vector_size ?? index?.vector_size ?? indexStatus?.indexed_vector_size;
  const statusError = indexStatus?.error ?? null;
  const lmStudioStatusError = embeddingProvider === "lm_studio" && statusError?.includes("LM Studio");

  // Determine the index badge
  const indexBadge = state === "loading"
    ? <Badge label="Indexing…" color="bg-amber-100 text-amber-700" />
    : indexed
    ? <Badge label={`Indexed (${indexedChunks})`} color="bg-sky-100 text-sky-700" />
    : <Badge label="Not indexed" color="bg-gray-100 text-gray-500" />;

  return (
    <Card
      title="Semantic Index"
      badge={
        statusLoading
          ? <Spinner className="w-3 h-3 border-gray-400" />
          : <div className="flex items-center gap-1.5">
              <QdrantBadge configured={qdrantConfigured} available={qdrantAvailable} />
              {indexBadge}
            </div>
      }
    >
      {/* Contextual messages */}
      {!statusLoading && !qdrantConfigured && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Qdrant is not configured. Run with Docker Compose or set <code className="font-mono">QDRANT_URL</code> to enable semantic search.
        </div>
      )}
      {!statusLoading && qdrantConfigured && !qdrantAvailable && !lmStudioStatusError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          Qdrant is configured but cannot be reached. Check that the Qdrant container is running.
        </div>
      )}
      {!statusLoading && lmStudioStatusError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {statusError}
        </div>
      )}
      {!statusLoading && qdrantConfigured && qdrantAvailable && !indexed && state !== "success" && (
        <p className="text-xs text-gray-500">
          This document is not indexed yet. Click <strong>Index for Semantic Search</strong> to enable semantic and hybrid search.
        </p>
      )}
      {!statusLoading && embeddingProvider && (
        <div className="space-y-1 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
          <Row label="Embedding provider" value={<span className="font-mono">{embeddingProvider}</span>} />
          {embeddingModel && <Row label="Embedding model" value={<span className="font-mono">{embeddingModel}</span>} />}
          {vectorSize != null && <Row label="Vector size" value={String(vectorSize)} />}
        </div>
      )}

      {/* Index button */}
      {state !== "success" && (
        <div className="grid grid-cols-2 gap-2">
          <ActionButton
            onClick={handleIndex}
            loading={state === "loading" && !indexJob}
            disabled={!qdrantConfigured || !qdrantAvailable}
            label={indexed ? "Re-index" : "Index"}
            loadingLabel="Indexing…"
            variant="secondary"
          />
          <ActionButton
            onClick={handleIndexJob}
            loading={!!indexJob && !isTerminalJob(indexJob)}
            disabled={!qdrantConfigured || !qdrantAvailable}
            label="Index Job"
            loadingLabel="Queued…"
            variant="secondary"
          />
        </div>
      )}
      <JobProgress job={indexJob} onCancel={handleCancelIndexJob} />

      {/* Error */}
      {state === "error" && error && (
        <p className="text-xs text-red-600">{error}</p>
      )}

      {/* Success details */}
      {state === "success" && index && (
        <div className="space-y-2">
          <Row label="Status" value={index.status} />
          <Row label="Indexed chunks" value={String(index.indexed_chunks)} />
          <Row label="Embedding provider" value={<span className="font-mono">{index.embedding_provider}</span>} />
          <Row label="Embedding model" value={<span className="font-mono">{index.embedding_model}</span>} />
          {index.vector_size != null && <Row label="Vector size" value={String(index.vector_size)} />}
          <Row label="Collection" value={<span className="font-mono">{index.collection_name}</span>} />
          <button onClick={handleIndex} className="text-xs text-sky-600 hover:text-sky-800">Re-index</button>
        </div>
      )}
    </Card>
  );
}

// ── Search panel ──────────────────────────────────────────────────────────────

type SearchMode = "keyword" | "semantic" | "hybrid";

interface DisplayResult {
  chunk_id: string; chunk_index: number; section_path: string[];
  content_type: string; score: number; estimated_tokens: number; text_preview: string;
}

function SearchPanel({ documentId, isIndexed }: { documentId: string; isIndexed: boolean }) {
  const [mode, setMode] = useState<SearchMode>("keyword");
  const [query, setQuery] = useState("");
  const [state, setState] = useState<AsyncState>("idle");
  const [results, setResults] = useState<DisplayResult[]>([]);
  const [hybridResults, setHybridResults] = useState<HybridResultItem[]>([]);
  const [meta, setMeta] = useState("");
  const [error, setError] = useState<string | null>(null);

  const MODES: { value: SearchMode; label: string }[] = [
    { value: "keyword",  label: "Keyword" },
    { value: "semantic", label: "Semantic" },
    { value: "hybrid",   label: "Hybrid" },
  ];

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setState("loading");
    setResults([]);
    setHybridResults([]);
    setError(null);
    try {
      if (mode === "keyword") {
        const data: SearchResponse = await searchDocument(documentId, query.trim());
        setResults(data.results);
        setMeta(`${data.results.length} results (${data.total_chunks_searched} chunks searched)`);
      } else if (mode === "semantic") {
        const data: SemanticSearchResponse = await semanticSearchDocument(documentId, query.trim());
        setResults(data.results.map((r) => ({ ...r })));
        setMeta(`${data.results.length} semantic results`);
      } else {
        const data: HybridSearchResponse = await hybridSearchDocument(documentId, query.trim());
        setHybridResults(data.results);
        setMeta(`${data.results.length} hybrid results${!data.semantic_available ? " (keyword only — index for semantic)" : ""}`);
      }
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setState("error");
    }
  }, [documentId, query, mode]);

  const semanticDisabled = (mode === "semantic") && !isIndexed;

  return (
    <Card title="Search Document">
      {/* Mode tabs */}
      <div className="flex gap-1 rounded-lg border border-gray-100 bg-gray-50 p-1">
        {MODES.map(({ value, label }) => {
          return (
            <button key={value} onClick={() => setMode(value)}
              className={["flex-1 py-1 rounded-md text-xs font-semibold transition-colors",
                mode === value ? "bg-white text-indigo-700 shadow-sm border border-gray-200" :
                "text-gray-500 hover:text-gray-700"].join(" ")}>
              {label}
            </button>
          );
        })}
      </div>
      {mode === "semantic" && !isIndexed && (
        <p className="text-xs text-amber-600">This document is not indexed. Click &quot;Index for Semantic Search&quot; above first.</p>
      )}
      {mode === "hybrid" && !isIndexed && (
        <p className="text-xs text-amber-600">Semantic index unavailable — hybrid results will use keyword search only.</p>
      )}
      <div className="flex gap-2">
        <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !semanticDisabled && handleSearch()}
          placeholder="Search your document…"
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
        <button onClick={handleSearch} disabled={!query.trim() || state === "loading" || semanticDisabled}
          title={semanticDisabled ? "Index this document first to use semantic search" : undefined}
          className={["px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
            !query.trim() || state === "loading" || semanticDisabled ? "bg-gray-100 text-gray-400" : "bg-indigo-600 text-white hover:bg-indigo-500"].join(" ")}>
          {state === "loading" ? <Spinner className="w-4 h-4 border-indigo-300" /> : "Search"}
        </button>
      </div>
      {state === "error" && error && <p className="text-xs text-red-600">{error}</p>}
      {state === "success" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400">{meta}</p>
          {mode !== "hybrid" && results.map((item) => {
            const bc = item.section_path.join(" › ") || "(root)";
            return (
              <div key={item.chunk_id} className="rounded-lg border border-gray-100 p-2.5 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-gray-400 truncate">{bc}</span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Badge label={item.content_type} color={CT_COLORS[item.content_type] ?? CT_COLORS.text} />
                    <span className="text-xs font-mono text-indigo-600">{item.score.toFixed(3)}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap line-clamp-3">{item.text_preview}</p>
              </div>
            );
          })}
          {mode === "hybrid" && hybridResults.map((item) => {
            const bc = item.section_path.join(" › ") || "(root)";
            return (
              <div key={item.chunk_id} className="rounded-lg border border-gray-100 p-2.5 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-gray-400 truncate">{bc}</span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Badge label={item.content_type} color={CT_COLORS[item.content_type] ?? CT_COLORS.text} />
                    <span className="text-xs font-mono font-bold text-indigo-700">{item.combined_score.toFixed(3)}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap line-clamp-3">{item.text_preview}</p>
                <div className="flex gap-3 text-xs text-gray-400">
                  <span>kw: <span className="font-mono">{item.keyword_score.toFixed(3)}</span></span>
                  <span>sem: <span className="font-mono">{item.semantic_score.toFixed(3)}</span></span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ── Ask panel ─────────────────────────────────────────────────────────────────

const GATEWAY_PROVIDERS: { value: GatewayProvider; label: string }[] = [
  { value: "mock",   label: "Mock (no API key)" },
  { value: "claude", label: "Claude" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Gemini" },
];

const RETRIEVAL_MODES: { value: RetrievalMode; label: string }[] = [
  { value: "hybrid",  label: "Hybrid" },
  { value: "keyword", label: "Keyword" },
  { value: "semantic",label: "Semantic" },
];

const EVIDENCE_COLORS: Record<string, string> = {
  strong: "bg-green-100 text-green-700",
  moderate: "bg-sky-100 text-sky-700",
  weak: "bg-amber-100 text-amber-700",
  none: "bg-gray-100 text-gray-500",
};

function AskPanel({ documentId, isIndexed, localOnlyMode }: { documentId: string; isIndexed: boolean; localOnlyMode: boolean }) {
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState<GatewayProvider>("mock");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(5);
  const [state, setState] = useState<AsyncState>("idle");
  const [response, setResponse] = useState<GroundedAnswerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedCitation, setCopiedCitation] = useState<string | null>(null);
  const [answerJob, setAnswerJob] = useState<JobDetail | null>(null);

  const semanticDisabled = mode === "semantic" && !isIndexed;

  const buildGroundedRequest = useCallback(() => ({
    question: query.trim(),
    retrieval_mode: mode,
    top_k: topK,
    provider,
  }), [query, mode, topK, provider]);

  const handleAsk = useCallback(async () => {
    if (!query.trim() || semanticDisabled) return;
    setState("loading");
    setResponse(null);
    setError(null);
    try {
      const data = await askGroundedAnswer(documentId, buildGroundedRequest());
      setResponse(data);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setState("error");
    }
  }, [documentId, query, buildGroundedRequest, semanticDisabled]);

  const handleAskJob = useCallback(async () => {
    if (!query.trim() || semanticDisabled) return;
    setState("loading");
    setResponse(null);
    setError(null);
    try {
      const job = await createGroundedAnswerJob(documentId, buildGroundedRequest());
      setAnswerJob(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Grounded answer job failed to start");
      setState("error");
    }
  }, [documentId, query, buildGroundedRequest, semanticDisabled]);

  const handleAnswerJobSucceeded = useCallback(async (job: JobDetail) => {
    if (job.result) {
      setResponse(job.result as unknown as GroundedAnswerResponse);
      setState("success");
    }
  }, []);

  useJobPolling(answerJob, setAnswerJob, handleAnswerJobSucceeded);

  const handleCancelAnswerJob = useCallback(async () => {
    if (!answerJob) return;
    try {
      setAnswerJob(await cancelJob(answerJob.job_id));
      setState("idle");
    } catch { /* ignore */ }
  }, [answerJob]);

  const isProviderWarn = response != null && provider !== "mock" &&
    (response.answer.includes("not configured") || response.answer.includes("is not set") ||
     response.answer.toLowerCase().includes("authentication failed") || response.answer.toLowerCase().includes("api error") ||
     response.answer.toLowerCase().includes("local-only mode"));

  const copyChunkId = useCallback((citationId: string, chunkId: string) => {
    navigator.clipboard.writeText(chunkId).then(() => {
      setCopiedCitation(citationId);
      setTimeout(() => setCopiedCitation(null), 1500);
    });
  }, []);

  return (
    <Card title="Ask Document">
      {localOnlyMode && provider !== "mock" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Local-only mode is enabled. External providers are blocked; use Mock for a local grounded response.
        </div>
      )}
      {!localOnlyMode && provider !== "mock" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          ⚠ This will send your document context to {provider}.
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <select value={provider} onChange={(e) => setProvider(e.target.value as GatewayProvider)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300">
          {GATEWAY_PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={mode} onChange={(e) => setMode(e.target.value as RetrievalMode)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300">
          {RETRIEVAL_MODES.map((m) => (
            <option key={m.value} value={m.value} disabled={m.value === "semantic" && !isIndexed}>
              {m.label}{m.value === "semantic" && !isIndexed ? " (index first)" : ""}
            </option>
          ))}
        </select>
        <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}
          className="w-20 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300">
          {[1, 3, 5, 10, 15, 20].map((k) => <option key={k} value={k}>top {k}</option>)}
        </select>
      </div>
      {mode === "semantic" && !isIndexed && (
        <p className="text-xs text-amber-600">Index this document first to use semantic grounded answers.</p>
      )}
      {mode === "hybrid" && !isIndexed && (
        <p className="text-xs text-amber-600">Semantic index unavailable — hybrid grounded answers will use keyword retrieval only.</p>
      )}
      <div className="flex gap-2">
        <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder="Ask a question about your document…"
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" />
        <button onClick={handleAsk} disabled={!query.trim() || state === "loading" || semanticDisabled}
          className={["px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
            !query.trim() || state === "loading" || semanticDisabled ? "bg-gray-100 text-gray-400" : "bg-emerald-600 text-white hover:bg-emerald-500"].join(" ")}>
          {state === "loading" ? <Spinner className="w-4 h-4 border-emerald-300" /> : "Ask"}
        </button>
        <button onClick={handleAskJob} disabled={!query.trim() || (!!answerJob && !isTerminalJob(answerJob)) || semanticDisabled}
          className={["px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
            !query.trim() || (!!answerJob && !isTerminalJob(answerJob)) || semanticDisabled ? "bg-gray-100 text-gray-400" : "bg-white text-emerald-700 border border-emerald-200 hover:bg-emerald-50"].join(" ")}>
          {!!answerJob && !isTerminalJob(answerJob) ? <Spinner className="w-4 h-4 border-emerald-300" /> : "Job"}
        </button>
      </div>
      <JobProgress job={answerJob} onCancel={handleCancelAnswerJob} />
      {state === "error" && error && <p className="text-xs text-red-600">{error}</p>}
      {state === "success" && response && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              label={`Evidence: ${response.evidence.evidence_strength}`}
              color={EVIDENCE_COLORS[response.evidence.evidence_strength] ?? EVIDENCE_COLORS.none}
            />
            <span className="text-xs text-gray-400">
              {response.evidence.citations_count} citation(s), {response.evidence.total_context_tokens.toLocaleString()} tokens
            </span>
          </div>
          {isProviderWarn ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">{response.answer}</div>
          ) : (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <p className="text-xs text-gray-400 mb-1.5">Answer</p>
              <pre className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed font-sans">{response.answer}</pre>
            </div>
          )}
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["Provider", response.provider], ["Retrieved", String(response.evidence.retrieved_chunks_count)], ["Top score", response.evidence.top_score == null ? "—" : response.evidence.top_score.toFixed(3)]].map(([l, v]) => (
              <div key={l} className="rounded-lg border border-gray-100 p-2">
                <p className="text-sm font-bold text-gray-900">{v}</p>
                <p className="text-xs text-gray-400">{l}</p>
              </div>
            ))}
          </div>
          {(response.warnings.length > 0 || response.evidence.warnings.length > 0) && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
              {Array.from(new Set([...response.warnings, ...response.evidence.warnings])).map((warning, i) => (
                <p key={i} className="text-xs text-amber-700">{warning}</p>
              ))}
            </div>
          )}
          {response.citations.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500">Citations</p>
              {response.citations.map((citation) => (
                <div key={citation.citation_id} className="rounded-lg border border-gray-100 p-2.5 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <Badge label={citation.citation_id} color="bg-emerald-100 text-emerald-700" />
                      <span className="truncate text-xs text-gray-500">{citation.source_label}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {citation.score != null && <span className="font-mono text-xs text-emerald-700">{citation.score.toFixed(3)}</span>}
                      <button
                        onClick={() => copyChunkId(citation.citation_id, citation.chunk_id)}
                        className="text-xs text-gray-400 hover:text-gray-700"
                      >
                        {copiedCitation === citation.citation_id ? "Copied" : "Copy ID"}
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap line-clamp-2">{citation.text_preview}</p>
                </div>
              ))}
            </div>
          )}
          {response.payload_id && (
            <p className="text-xs text-gray-400 font-mono truncate">Payload: {response.payload_id}</p>
          )}
        </div>
      )}
    </Card>
  );
}

// ── LLM payload panel ─────────────────────────────────────────────────────────

const LLM_PROVIDERS: { value: LLMProvider; label: string }[] = [
  { value: "claude",  label: "Claude (XML)" },
  { value: "openai",  label: "OpenAI (Markdown)" },
  { value: "gemini",  label: "Gemini (Markdown)" },
  { value: "generic", label: "Generic (Markdown)" },
];

function LLMPayloadPanel({ documentId }: { documentId: string }) {
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState<LLMProvider>("generic");
  const [topK, setTopK] = useState(5);
  const [state, setState] = useState<AsyncState>("idle");
  const [payload, setPayload] = useState<LLMPayloadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCtx, setShowCtx] = useState(false);
  const [showJson, setShowJson] = useState(false);

  const handlePrepare = useCallback(async () => {
    if (!query.trim()) return;
    setState("loading");
    setPayload(null);
    setError(null);
    setShowCtx(false);
    setShowJson(false);
    try {
      const data = await prepareLlmPayload(documentId, query.trim(), topK, provider);
      setPayload(data);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to prepare payload");
      setState("error");
    }
  }, [documentId, query, topK, provider]);

  return (
    <Card title="Prepare LLM Payload">
      <div className="flex gap-2">
        <select value={provider} onChange={(e) => setProvider(e.target.value as LLMProvider)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-violet-300">
          {LLM_PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}
          className="w-20 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-violet-300">
          {[1, 3, 5, 10, 15, 20].map((k) => <option key={k} value={k}>top {k}</option>)}
        </select>
      </div>
      <div className="flex gap-2">
        <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handlePrepare()}
          placeholder="Enter your query…"
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-300" />
        <button onClick={handlePrepare} disabled={!query.trim() || state === "loading"}
          className={["px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
            !query.trim() || state === "loading" ? "bg-gray-100 text-gray-400" : "bg-violet-600 text-white hover:bg-violet-500"].join(" ")}>
          {state === "loading" ? <Spinner className="w-4 h-4 border-violet-300" /> : "Prepare"}
        </button>
      </div>
      {state === "error" && error && <p className="text-xs text-red-600">{error}</p>}
      {state === "success" && payload && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["Chunks", String(payload.chunks_used)], ["Tokens", payload.total_estimated_tokens.toLocaleString()], ["Provider", payload.provider]].map(([l, v]) => (
              <div key={l} className="rounded-lg border border-gray-100 p-2">
                <p className="text-sm font-bold text-gray-900">{v}</p>
                <p className="text-xs text-gray-400">{l}</p>
              </div>
            ))}
          </div>
          <div className={["flex items-center gap-2 rounded-lg border px-3 py-2 text-xs",
            payload.integrity.all_chunks_verified ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"].join(" ")}>
            <span className="font-bold">{payload.integrity.all_chunks_verified ? "✓" : "✕"}</span>
            {payload.integrity.all_chunks_verified ? `All ${payload.integrity.verified_count} chunks verified` : `${payload.integrity.failed_chunk_ids.length} chunk(s) failed verification`}
          </div>
          <button onClick={() => setShowCtx((v) => !v)} className="text-xs text-violet-700 hover:text-violet-500 font-medium">
            {showCtx ? "Hide" : "Show"} formatted context
          </button>
          {showCtx && (
            <pre className="overflow-auto max-h-48 rounded-lg bg-gray-950 text-gray-100 text-xs p-3 whitespace-pre-wrap break-words">
              {payload.formatted_context}
            </pre>
          )}
          <button onClick={() => setShowJson((v) => !v)} className="text-xs text-violet-700 hover:text-violet-500 font-medium">
            {showJson ? "Hide" : "Show"} JSON payload
          </button>
          {showJson && (
            <pre className="overflow-auto max-h-48 rounded-lg bg-gray-950 text-gray-100 text-xs p-3 whitespace-pre-wrap break-words">
              {JSON.stringify(payload.universal_payload, null, 2)}
            </pre>
          )}
        </div>
      )}
    </Card>
  );
}

// ── Token budget panel ────────────────────────────────────────────────────────

function TokenBudgetPanel({ documentId }: { documentId: string }) {
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState(8000);
  const [state, setState] = useState<AsyncState>("idle");
  const [estimate, setEstimate] = useState<EstimateContextResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleEstimate = useCallback(async () => {
    if (!query.trim()) return;
    setState("loading");
    setEstimate(null);
    setError(null);
    try {
      const data = await estimateContext(documentId, query.trim(), budget);
      setEstimate(data);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Estimation failed");
      setState("error");
    }
  }, [documentId, query, budget]);

  const BUDGETS = [{ v: 4000, l: "4k" }, { v: 8000, l: "8k" }, { v: 16000, l: "16k" }];

  return (
    <Card title="Token Budget Estimator">
      <div className="flex gap-1 rounded-lg border border-gray-100 bg-gray-50 p-1">
        {BUDGETS.map(({ v, l }) => (
          <button key={v} onClick={() => setBudget(v)}
            className={["flex-1 py-1 rounded-md text-xs font-semibold transition-colors",
              budget === v ? "bg-amber-500 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"].join(" ")}>
            {l} tokens
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleEstimate()}
          placeholder="Enter query to estimate context…"
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300" />
        <button onClick={handleEstimate} disabled={!query.trim() || state === "loading"}
          className={["px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
            !query.trim() || state === "loading" ? "bg-gray-100 text-gray-400" : "bg-amber-500 text-white hover:bg-amber-400"].join(" ")}>
          {state === "loading" ? <Spinner className="w-4 h-4 border-amber-200" /> : "Estimate"}
        </button>
      </div>
      {state === "error" && error && <p className="text-xs text-red-600">{error}</p>}
      {state === "success" && estimate && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["Selected", String(estimate.selected_chunk_count)], ["Tokens", estimate.estimated_context_tokens.toLocaleString()], ["Skipped", String(estimate.skipped_chunks_due_to_budget)]].map(([l, v]) => (
              <div key={l} className="rounded-lg border border-amber-100 p-2">
                <p className="text-sm font-bold text-gray-900">{v}</p>
                <p className="text-xs text-gray-400">{l}</p>
              </div>
            ))}
          </div>
          <div>
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Usage</span>
              <span>{estimate.estimated_context_tokens.toLocaleString()} / {estimate.budget_used.toLocaleString()}</span>
            </div>
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div className="h-full rounded-full bg-amber-400 transition-all"
                style={{ width: `${Math.min(100, (estimate.estimated_context_tokens / estimate.budget_used) * 100)}%` }} />
            </div>
          </div>
          {estimate.skipped_chunks_due_to_budget > 0 && (
            <p className="text-xs text-amber-700">{estimate.skipped_chunks_due_to_budget} chunk(s) skipped — increase budget to include more context.</p>
          )}
        </div>
      )}
    </Card>
  );
}

// ── Job history panel ────────────────────────────────────────────────────────

const JOB_STATUS_COLORS: Record<string, string> = {
  queued: "bg-gray-100 text-gray-600",
  running: "bg-indigo-100 text-indigo-700",
  succeeded: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  canceled: "bg-amber-100 text-amber-700",
};

function JobHistoryPanel({ documentId }: { documentId: string }) {
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [state, setState] = useState<AsyncState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    let stale = false;
    listDocumentJobs(documentId)
      .then((data) => {
        if (stale) return;
        setJobs(data.jobs);
        setState("success");
      })
      .catch((err) => {
        if (stale) return;
        setError(err instanceof Error ? err.message : "Failed to load jobs");
        setState("error");
      });
    return () => { stale = true; };
  }, [documentId, reloadCount]);

  const reloadJobs = useCallback(() => {
    setState("loading");
    setError(null);
    setReloadCount((c) => c + 1);
  }, []);

  const handleCancel = useCallback(async (jobId: string) => {
    setBusy(jobId);
    try {
      await cancelJob(jobId);
      reloadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setBusy(null);
    }
  }, [reloadJobs]);

  const handleRetry = useCallback(async (jobId: string) => {
    setBusy(jobId);
    try {
      await retryJob(jobId);
      reloadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setBusy(null);
    }
  }, [reloadJobs]);

  return (
    <Card
      title="Job History"
      badge={<a href={`/jobs?document_id=${documentId}`} className="text-xs text-indigo-600 hover:text-indigo-800">All jobs</a>}
    >
      {state === "loading" && <p className="text-xs text-gray-400">Loading jobs…</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
      {state === "success" && jobs.length === 0 && (
        <p className="text-xs text-gray-400">No background jobs for this document yet.</p>
      )}
      {jobs.length > 0 && (
        <div className="space-y-2">
          {jobs.slice(0, 8).map((job) => {
            const isExpanded = expanded === job.job_id;
            return (
              <div key={job.job_id} className="rounded-lg border border-gray-100 p-2.5 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge label={job.status} color={JOB_STATUS_COLORS[job.status] ?? JOB_STATUS_COLORS.queued} />
                  <button onClick={() => setExpanded(isExpanded ? null : job.job_id)}
                    className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-gray-700 hover:text-indigo-700">
                    {job.job_type}
                  </button>
                  <span className="text-xs text-gray-400 shrink-0">{job.progress_percent}%</span>
                  {job.can_cancel && (
                    <button onClick={() => handleCancel(job.job_id)} disabled={busy === job.job_id}
                      className="text-xs text-gray-500 hover:text-red-600 disabled:text-gray-300">
                      Cancel
                    </button>
                  )}
                  {job.can_retry && (
                    <button onClick={() => handleRetry(job.job_id)} disabled={busy === job.job_id}
                      className="text-xs text-indigo-600 hover:text-indigo-800 disabled:text-gray-300">
                      Retry
                    </button>
                  )}
                </div>
                <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                  <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.min(100, Math.max(0, job.progress_percent))}%` }} />
                </div>
                {isExpanded && (
                  <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs space-y-1">
                    <Row label="Updated" value={job.updated_at ? formatDate(job.updated_at) : "—"} />
                    <Row label="Step" value={job.current_step ?? "—"} />
                    <Row label="Message" value={job.message ?? "—"} />
                    {job.retry_of_job_id && <Row label="Retry of" value={<span className="font-mono">{job.retry_of_job_id}</span>} />}
                    {job.error && <p className="text-red-600">{job.error}</p>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ── Evaluation panel ─────────────────────────────────────────────────────────

function EvaluationPanel({ documentId, isIndexed }: { documentId: string; isIndexed: boolean }) {
  const [qualityState, setQualityState] = useState<AsyncState>("idle");
  const [quality, setQuality] = useState<ChunkQualityReport | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);

  const [tokenState, setTokenState] = useState<AsyncState>("idle");
  const [tokenEfficiency, setTokenEfficiency] = useState<TokenEfficiencySummary | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const [mode, setMode] = useState<RetrievalMode>("keyword");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [expectedTerms, setExpectedTerms] = useState("");
  const [expectedSection, setExpectedSection] = useState("");
  const [retrievalState, setRetrievalState] = useState<AsyncState>("idle");
  const [retrieval, setRetrieval] = useState<RetrievalEvaluationResponse | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);
  const [retrievalJob, setRetrievalJob] = useState<JobDetail | null>(null);

  const [setInput, setSetInput] = useState("");
  const [evaluationSetState, setEvaluationSetState] = useState<AsyncState>("idle");
  const [setResult, setSetResult] = useState<RetrievalEvaluationSetResponse | null>(null);
  const [setError, setSetError] = useState<string | null>(null);

  const currentEfficiency = retrieval?.token_efficiency_estimate ?? tokenEfficiency;
  const semanticBlocked = mode === "semantic" && !isIndexed;

  const buildRetrievalRequest = useCallback(() => ({
    query: query.trim(),
    retrieval_mode: mode,
    top_k: topK,
    expected_terms: expectedTerms.split(",").map((term) => term.trim()).filter(Boolean),
    expected_section: expectedSection.trim() || null,
  }), [query, mode, topK, expectedTerms, expectedSection]);

  const loadQuality = useCallback(async () => {
    setQualityState("loading");
    setQuality(null);
    setQualityError(null);
    try {
      const data = await fetchChunkQuality(documentId);
      setQuality(data);
      setQualityState("success");
    } catch (err) {
      setQualityError(err instanceof Error ? err.message : "Quality evaluation failed");
      setQualityState("error");
    }
  }, [documentId]);

  const loadTokenEfficiency = useCallback(async () => {
    setTokenState("loading");
    setTokenEfficiency(null);
    setTokenError(null);
    try {
      const data = await fetchTokenEfficiency(documentId);
      setTokenEfficiency(data);
      setTokenState("success");
    } catch (err) {
      setTokenError(err instanceof Error ? err.message : "Token efficiency failed");
      setTokenState("error");
    }
  }, [documentId]);

  const runRetrievalEvaluation = useCallback(async () => {
    if (!query.trim() || semanticBlocked) return;
    setRetrievalState("loading");
    setRetrieval(null);
    setRetrievalError(null);
    try {
      const data = await evaluateRetrieval(documentId, {
        ...buildRetrievalRequest(),
      });
      setRetrieval(data);
      setRetrievalState("success");
    } catch (err) {
      setRetrievalError(err instanceof Error ? err.message : "Retrieval evaluation failed");
      setRetrievalState("error");
    }
  }, [documentId, query, buildRetrievalRequest, semanticBlocked]);

  const runRetrievalEvaluationJob = useCallback(async () => {
    if (!query.trim() || semanticBlocked) return;
    setRetrievalState("loading");
    setRetrieval(null);
    setRetrievalError(null);
    try {
      const job = await createRetrievalEvaluationJob(documentId, buildRetrievalRequest());
      setRetrievalJob(job);
    } catch (err) {
      setRetrievalError(err instanceof Error ? err.message : "Retrieval evaluation job failed to start");
      setRetrievalState("error");
    }
  }, [documentId, query, buildRetrievalRequest, semanticBlocked]);

  const handleRetrievalJobSucceeded = useCallback(async (job: JobDetail) => {
    if (job.result) {
      setRetrieval(job.result as unknown as RetrievalEvaluationResponse);
      setRetrievalState("success");
    }
  }, []);

  useJobPolling(retrievalJob, setRetrievalJob, handleRetrievalJobSucceeded);

  const handleCancelRetrievalJob = useCallback(async () => {
    if (!retrievalJob) return;
    try {
      setRetrievalJob(await cancelJob(retrievalJob.job_id));
      setRetrievalState("idle");
    } catch { /* ignore */ }
  }, [retrievalJob]);

  const runEvaluationSet = useCallback(async () => {
    const queries = setInput
      .split("\n")
      .map((line) => {
        const [q, terms = "", section = ""] = line.split("|").map((part) => part.trim());
        if (!q) return null;
        return {
          query: q,
          expected_terms: terms.split(",").map((term) => term.trim()).filter(Boolean),
          expected_section: section || null,
        };
      })
      .filter((item): item is { query: string; expected_terms: string[]; expected_section: string | null } => item !== null);

    if (queries.length === 0 || semanticBlocked) return;
    setEvaluationSetState("loading");
    setSetResult(null);
    setSetError(null);
    try {
      const data = await evaluateRetrievalSet(documentId, mode, topK, queries);
      setSetResult(data);
      setEvaluationSetState("success");
    } catch (err) {
      setSetError(err instanceof Error ? err.message : "Evaluation set failed");
      setEvaluationSetState("error");
    }
  }, [documentId, mode, topK, setInput, semanticBlocked]);

  return (
    <Card title="Evaluation">
      <div className="space-y-3">
        <div className="rounded-lg border border-gray-100 p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold text-gray-600">Chunk Quality</p>
            <button
              onClick={loadQuality}
              disabled={qualityState === "loading"}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:bg-gray-50 disabled:text-gray-400"
            >
              {qualityState === "loading" ? "Analyzing…" : "Analyze"}
            </button>
          </div>
          {qualityState === "error" && qualityError && <p className="text-xs text-red-600">{qualityError}</p>}
          {quality && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  ["Score", quality.quality_score.toFixed(1)],
                  ["Chunks", quality.total_chunks.toLocaleString()],
                  ["Avg tokens", quality.average_chunk_tokens.toLocaleString()],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-gray-100 bg-gray-50 p-2">
                    <p className="text-sm font-bold text-gray-900">{value}</p>
                    <p className="text-xs text-gray-400">{label}</p>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Row label="Token range" value={`${quality.min_chunk_tokens.toLocaleString()}–${quality.max_chunk_tokens.toLocaleString()}`} />
                <Row label="Section paths" value={formatPercent(quality.section_path_coverage_percent)} />
                <Row label="Oversized" value={quality.oversized_chunks_count.toLocaleString()} />
                <Row label="Undersized" value={quality.undersized_chunks_count.toLocaleString()} />
              </div>
              {quality.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                  {quality.warnings.map((warning, i) => (
                    <p key={i} className="text-xs text-amber-700">{warning}</p>
                  ))}
                </div>
              )}
              {quality.recommendations.length > 0 && (
                <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                  {quality.recommendations.map((item, i) => (
                    <p key={i} className="text-xs text-gray-600">{item}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="rounded-lg border border-gray-100 p-3 space-y-2">
          <p className="text-xs font-semibold text-gray-600">Retrieval Evaluation</p>
          <div className="flex flex-wrap gap-2">
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as RetrievalMode)}
              className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              {RETRIEVAL_MODES.map((item) => (
                <option key={item.value} value={item.value} disabled={item.value === "semantic" && !isIndexed}>
                  {item.label}{item.value === "semantic" && !isIndexed ? " (index first)" : ""}
                </option>
              ))}
            </select>
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-20 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              {[1, 3, 5, 10, 15, 20].map((k) => <option key={k} value={k}>top {k}</option>)}
            </select>
          </div>
          {mode === "hybrid" && !isIndexed && (
            <p className="text-xs text-amber-600">Semantic index unavailable — hybrid evaluation will use keyword results only.</p>
          )}
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runRetrievalEvaluation()}
            placeholder="Query"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              value={expectedTerms}
              onChange={(e) => setExpectedTerms(e.target.value)}
              placeholder="Expected terms"
              className="min-w-0 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <input
              type="text"
              value={expectedSection}
              onChange={(e) => setExpectedSection(e.target.value)}
              placeholder="Expected section"
              className="min-w-0 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <ActionButton
              onClick={runRetrievalEvaluation}
              loading={retrievalState === "loading" && !retrievalJob}
              disabled={!query.trim() || semanticBlocked}
              label="Evaluate"
              loadingLabel="Evaluating…"
              variant="secondary"
            />
            <ActionButton
              onClick={runRetrievalEvaluationJob}
              loading={!!retrievalJob && !isTerminalJob(retrievalJob)}
              disabled={!query.trim() || semanticBlocked}
              label="Evaluate Job"
              loadingLabel="Queued…"
              variant="secondary"
            />
          </div>
          <JobProgress job={retrievalJob} onCancel={handleCancelRetrievalJob} />
          {retrievalState === "error" && retrievalError && <p className="text-xs text-red-600">{retrievalError}</p>}
          {retrieval && (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  ["Score", retrieval.retrieval_score_estimate.toFixed(1)],
                  ["Chunks", retrieval.returned_chunks_count.toLocaleString()],
                  ["Tokens", retrieval.total_context_tokens.toLocaleString()],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-gray-100 bg-gray-50 p-2">
                    <p className="text-sm font-bold text-gray-900">{value}</p>
                    <p className="text-xs text-gray-400">{label}</p>
                  </div>
                ))}
              </div>
              <Row label="Top score" value={retrieval.top_score == null ? "—" : retrieval.top_score.toFixed(3)} />
              <Row label="Expected terms" value={`${retrieval.expected_terms_found.length} found, ${retrieval.expected_terms_missing.length} missing`} />
              {retrieval.expected_section && (
                <Row label="Section hit" value={retrieval.expected_section_hit ? "Yes" : "No"} />
              )}
              {retrieval.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                  {retrieval.warnings.map((warning, i) => (
                    <p key={i} className="text-xs text-amber-700">{warning}</p>
                  ))}
                </div>
              )}
              {retrieval.selected_results.slice(0, 3).map((item) => {
                const bc = item.section_path.join(" › ") || "(root)";
                return (
                  <div key={item.chunk_id} className="rounded-lg border border-gray-100 p-2.5 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-gray-400 truncate">{bc}</span>
                      <span className="text-xs font-mono text-indigo-600">{item.score.toFixed(3)}</span>
                    </div>
                    <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap line-clamp-2">{item.text_preview}</p>
                  </div>
                );
              })}
            </div>
          )}
          <textarea
            value={setInput}
            onChange={(e) => setSetInput(e.target.value)}
            placeholder="query | expected terms | expected section"
            rows={3}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            onClick={runEvaluationSet}
            disabled={!setInput.trim() || evaluationSetState === "loading" || semanticBlocked}
            className={[
              "w-full rounded-lg border px-3 py-2 text-xs font-semibold transition-colors",
              !setInput.trim() || evaluationSetState === "loading" || semanticBlocked
                ? "border-gray-100 bg-gray-50 text-gray-400"
                : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50",
            ].join(" ")}
          >
            {evaluationSetState === "loading" ? "Evaluating set…" : "Evaluate Set"}
          </button>
          {evaluationSetState === "error" && setError && <p className="text-xs text-red-600">{setError}</p>}
          {setResult && (
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                ["Queries", setResult.total_queries.toLocaleString()],
                ["Avg score", setResult.average_retrieval_score_estimate.toFixed(1)],
                ["Avg tokens", setResult.average_context_tokens.toLocaleString()],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-gray-100 bg-gray-50 p-2">
                  <p className="text-sm font-bold text-gray-900">{value}</p>
                  <p className="text-xs text-gray-400">{label}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-100 p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold text-gray-600">Token Efficiency</p>
            <button
              onClick={loadTokenEfficiency}
              disabled={tokenState === "loading"}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:bg-gray-50 disabled:text-gray-400"
            >
              {tokenState === "loading" ? "Refreshing…" : "Refresh"}
            </button>
          </div>
          {tokenState === "error" && tokenError && <p className="text-xs text-red-600">{tokenError}</p>}
          {currentEfficiency && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  ["Converted", currentEfficiency.converted_estimated_tokens?.toLocaleString() ?? "—"],
                  ["Chunks", currentEfficiency.total_chunk_tokens?.toLocaleString() ?? "—"],
                  ["Selected", currentEfficiency.selected_context_tokens?.toLocaleString() ?? "—"],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-gray-100 bg-gray-50 p-2">
                    <p className="text-sm font-bold text-gray-900">{value}</p>
                    <p className="text-xs text-gray-400">{label}</p>
                  </div>
                ))}
              </div>
              <Row label="Reduction vs converted" value={formatPercent(currentEfficiency.token_reduction_percent_vs_converted)} />
              <p className="text-xs text-gray-600">{currentEfficiency.interpretation}</p>
              {currentEfficiency.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                  {currentEfficiency.warnings.map((warning, i) => (
                    <p key={i} className="text-xs text-amber-700">{warning}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

// ── Audit timeline ────────────────────────────────────────────────────────────

const EVT_COLORS: Record<string, string> = {
  upload:    "bg-blue-100 text-blue-700",
  profile:   "bg-indigo-100 text-indigo-700",
  pipeline:  "bg-purple-100 text-purple-700",
  convert:   "bg-amber-100 text-amber-700",
  chunk:     "bg-green-100 text-green-700",
  integrity: "bg-teal-100 text-teal-700",
  llm_call:  "bg-emerald-100 text-emerald-700",
  security:  "bg-slate-100 text-slate-700",
};

function AuditTimeline({ events }: { events: AuditEventItem[] }) {
  if (events.length === 0) return null;
  return (
    <Card title={`Audit Timeline (${events.length} events)`}>
      <div className="space-y-1.5">
        {events.map((e) => {
          const color = EVT_COLORS[e.event_type] ?? "bg-gray-100 text-gray-600";
          return (
            <div key={e.id} className="flex items-center gap-3 py-1 border-b border-gray-50 last:border-0">
              <Badge label={e.event_type} color={color} />
              <span className="text-xs text-gray-400 shrink-0 ml-auto">{formatDate(e.created_at)}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Document preview panel ────────────────────────────────────────────────────

function PreviewPanel({ documentId }: { documentId: string }) {
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [state, setState] = useState<AsyncState>("loading");
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchDocumentPreview(documentId)
      .then((data) => { setPreview(data); setState("success"); })
      .catch(() => setState("error"));
  }, [documentId]);

  const handleCopy = useCallback(() => {
    if (!preview?.preview) return;
    navigator.clipboard.writeText(preview.preview).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [preview]);

  if (state === "loading") {
    return (
      <Card title="Document Preview">
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Spinner className="w-3 h-3 border-gray-400" /> Loading preview…
        </div>
      </Card>
    );
  }

  if (state === "error") {
    return (
      <Card title="Document Preview">
        <p className="text-xs text-gray-400">Preview unavailable.</p>
      </Card>
    );
  }

  if (!preview?.exists) {
    return (
      <Card title="Document Preview">
        <p className="text-xs text-gray-400">
          Document has not been converted yet. Run <strong>Convert Document</strong> to generate a preview.
        </p>
      </Card>
    );
  }

  const displayText = expanded ? preview.preview : preview.preview.slice(0, 1200);
  const showToggle = preview.preview.length > 1200;

  return (
    <Card
      title="Document Preview"
      badge={
        preview.truncated ? (
          <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700">
            truncated at {(preview.char_count / 1000).toFixed(0)}k chars
          </span>
        ) : (
          <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-500">
            {preview.char_count.toLocaleString()} chars
          </span>
        )
      }
    >
      <pre className="overflow-auto rounded-lg bg-gray-950 text-gray-100 text-xs p-3 leading-relaxed whitespace-pre-wrap break-words max-h-72">
        {displayText}
        {!expanded && showToggle && (
          <span className="text-gray-500">…</span>
        )}
      </pre>
      <div className="flex items-center gap-3">
        {showToggle && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
          >
            {expanded ? "Show less" : `Show more (${preview.preview.length.toLocaleString()} chars)`}
          </button>
        )}
        <button
          onClick={handleCopy}
          className="text-xs text-gray-500 hover:text-gray-700 ml-auto"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, string> = {
  pass:    "bg-green-100 text-green-700 border-green-200",
  warn:    "bg-amber-50 text-amber-700 border-amber-200",
  fail:    "bg-red-100 text-red-700 border-red-200",
  success: "bg-green-100 text-green-700 border-green-200",
  partial: "bg-amber-50 text-amber-700 border-amber-200",
  failed:  "bg-red-100 text-red-700 border-red-200",
  raw:     "bg-gray-100 text-gray-600 border-gray-200",
};

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const documentId = params.id;

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Pipeline state
  const [profileState, setProfileState] = useState<AsyncState>("idle");
  const [profile, setProfile] = useState<DocumentProfile | null>(null);

  const [pipelineState, setPipelineState] = useState<AsyncState>("idle");
  const [pipeline, setPipeline] = useState<PipelineDecision | null>(null);

  const [conversionState, setConversionState] = useState<AsyncState>("idle");
  const [conversion, setConversion] = useState<ConversionResult | null>(null);
  const [conversionJob, setConversionJob] = useState<JobDetail | null>(null);

  const [chunkState, setChunkState] = useState<AsyncState>("idle");
  const [chunking, setChunking] = useState<ChunkingResult | null>(null);
  const [chunkJob, setChunkJob] = useState<JobDetail | null>(null);

  const [integrityState, setIntegrityState] = useState<AsyncState>("idle");
  const [integrity, setIntegrity] = useState<IntegrityReport | null>(null);

  const [isIndexed, setIsIndexed] = useState(false);
  const [localOnlyMode, setLocalOnlyMode] = useState(false);
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [initializing, setInitializing] = useState(false);

  // Current active step for pipeline tracker animation
  const activeStep =
    profileState === "loading"   ? "profiled"          :
    pipelineState === "loading"  ? "pipeline_decided"  :
    conversionState === "loading"? "converted"         :
    chunkState === "loading"     ? "chunked"           : undefined;

  useEffect(() => {
    if (!documentId) return;

    fetchHealth().then((h) => setLocalOnlyMode(h.local_only_mode)).catch(() => {});

    async function load() {
      try {
        let detail = await getDocumentDetail(documentId);

        // Auto-initialize: run profile + pipeline if either is missing
        if (!detail.profile || !detail.pipeline) {
          setInitializing(true);
          try {
            await initializeDocument(documentId);
            detail = await getDocumentDetail(documentId);
          } catch { /* non-critical — manual buttons still available */ }
          setInitializing(false);
        }

        setDoc(detail);

        // Load existing conversion if done
        if (detail.conversion) {
          try {
            const conv = await getConverted(documentId);
            setConversion(conv);
            setConversionState("success");
          } catch { /* file might not exist yet */ }
        }

        // Load existing chunks if done
        if (detail.chunks) {
          try {
            const chunks = await getChunks(documentId);
            setChunking(chunks);
            setChunkState("success");
          } catch { /* file might not exist yet */ }
        }

        // Load audit events
        try {
          const audit = await getDocumentAudit(documentId, 20);
          setAuditEvents(audit.events);
        } catch { /* non-critical */ }
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Failed to load document");
        setInitializing(false);
      }
    }
    load();
  }, [documentId]);

  // Refresh doc summary from DB
  const refreshDoc = useCallback(async () => {
    try {
      const updated = await getDocumentDetail(documentId);
      setDoc(updated);
      const audit = await getDocumentAudit(documentId, 20);
      setAuditEvents(audit.events);
    } catch { /* ignore */ }
  }, [documentId]);

  const handleProfile = useCallback(async () => {
    setProfileState("loading");
    setProfile(null);
    try {
      const data = await fetchProfile(documentId);
      setProfile(data);
      setProfileState("success");
      await refreshDoc();
    } catch {
      setProfileState("error");
    }
  }, [documentId, refreshDoc]);

  const handlePipeline = useCallback(async () => {
    setPipelineState("loading");
    setPipeline(null);
    try {
      const data = await fetchPipeline(documentId);
      setPipeline(data);
      setPipelineState("success");
      await refreshDoc();
    } catch {
      setPipelineState("error");
    }
  }, [documentId, refreshDoc]);

  const handleConvert = useCallback(async () => {
    setConversionState("loading");
    setConversion(null);
    try {
      const data = await convertDocument(documentId);
      setConversion(data);
      setConversionState("success");
      await refreshDoc();
    } catch {
      setConversionState("error");
    }
  }, [documentId, refreshDoc]);

  const handleConvertJob = useCallback(async () => {
    setConversionState("loading");
    try {
      const job = await createConvertJob(documentId);
      setConversionJob(job);
    } catch {
      setConversionState("error");
    }
  }, [documentId]);

  const handleConversionJobSucceeded = useCallback(async () => {
    try {
      const data = await getConverted(documentId);
      setConversion(data);
      setConversionState("success");
      await refreshDoc();
    } catch {
      setConversionState("error");
    }
  }, [documentId, refreshDoc]);

  useJobPolling(conversionJob, setConversionJob, handleConversionJobSucceeded);

  const handleCancelConversionJob = useCallback(async () => {
    if (!conversionJob) return;
    try {
      setConversionJob(await cancelJob(conversionJob.job_id));
      setConversionState("idle");
    } catch { /* ignore */ }
  }, [conversionJob]);

  const handleChunk = useCallback(async () => {
    setChunkState("loading");
    setChunking(null);
    try {
      const data = await chunkDocument(documentId);
      setChunking(data);
      setChunkState("success");
      await refreshDoc();
    } catch {
      setChunkState("error");
    }
  }, [documentId, refreshDoc]);

  const handleChunkJob = useCallback(async () => {
    setChunkState("loading");
    try {
      const job = await createChunkJob(documentId);
      setChunkJob(job);
    } catch {
      setChunkState("error");
    }
  }, [documentId]);

  const handleChunkJobSucceeded = useCallback(async () => {
    try {
      const data = await getChunks(documentId);
      setChunking(data);
      setChunkState("success");
      await refreshDoc();
    } catch {
      setChunkState("error");
    }
  }, [documentId, refreshDoc]);

  useJobPolling(chunkJob, setChunkJob, handleChunkJobSucceeded);

  const handleCancelChunkJob = useCallback(async () => {
    if (!chunkJob) return;
    try {
      setChunkJob(await cancelJob(chunkJob.job_id));
      setChunkState("idle");
    } catch { /* ignore */ }
  }, [chunkJob]);

  const handleIntegrity = useCallback(async () => {
    setIntegrityState("loading");
    setIntegrity(null);
    try {
      const data = await fetchIntegrity(documentId);
      setIntegrity(data);
      setIntegrityState("success");
    } catch {
      setIntegrityState("error");
    }
  }, [documentId]);

  if (loadError) {
    return (
      <main className="max-w-3xl mx-auto px-6 py-10">
        <div
          className="rounded-[var(--radius-xs)] border px-4 py-3 text-sm"
          style={{ background: "#fde8e6", borderColor: "#f7cbc6", color: "#c2382b" }}
        >
          {loadError}
        </div>
      </main>
    );
  }

  if (!doc) {
    return (
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-2">
        <p className="text-sm animate-pulse" style={{ color: "var(--text-3)" }}>Loading…</p>
        {initializing && (
          <p className="text-xs animate-pulse" style={{ color: "var(--a-soft-fg)" }}>Analyzing document…</p>
        )}
      </main>
    );
  }

  const phase = doc.current_phase;
  const isChunked = phase === "chunked" || chunkState === "success";

  // Compute next recommended action
  const nextAction: { label: string; hint: string } | null = (() => {
    if (isChunked) return { label: "Search or prepare payload", hint: "Use the panels below to search, ask, or build an LLM payload." };
    if (conversion || conversionState === "success") return { label: "Generate Chunks", hint: "Split the converted document into searchable chunks." };
    if (doc.pipeline || pipeline) return { label: "Convert Document", hint: "Convert the document to Markdown for further processing." };
    if (doc.profile || profile) return { label: "Select Pipeline", hint: "Choose the conversion pipeline for this document type." };
    return { label: "Analyze Document", hint: "Profile the document to detect its type and recommend a processing pipeline." };
  })();

  return (
    <main className="max-w-3xl mx-auto px-6 py-8 space-y-4 fade-in">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-3)" }}>
        <Link href="/" className="hover:underline" style={{ color: "var(--a-soft-fg)" }}>Dashboard</Link>
        <span>/</span>
        <Link href="/documents" className="hover:underline" style={{ color: "var(--a-soft-fg)" }}>Documents</Link>
        <span>/</span>
        <span className="truncate max-w-xs" style={{ color: "var(--text)" }}>{doc.original_filename}</span>
      </nav>

      {/* Header */}
      <div>
        <h1 className="text-[1.55rem] font-bold tracking-tight leading-snug" style={{ color: "var(--text)" }}>
          {doc.original_filename}
        </h1>
        <p className="text-xs font-mono mt-1" style={{ color: "var(--text-3)" }}>{doc.document_id}</p>
      </div>

      {/* Initializing indicator */}
      {initializing && (
        <div
          className="flex items-center gap-2 rounded-[var(--radius-xs)] border px-3 py-2 text-xs"
          style={{ background: "var(--a-soft)", borderColor: "rgba(91,80,240,0.2)", color: "var(--a-soft-fg)" }}
        >
          <Spinner className="w-3 h-3 border-current" />
          Analyzing document…
        </div>
      )}

      {/* Pipeline tracker */}
      <div
        className="rounded-[var(--radius)] p-5"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--card-shadow)" }}
      >
        <PipelineTracker currentPhase={phase} activeStep={initializing ? "profiled" : activeStep} />
      </div>

      {/* Next recommended action */}
      {!isChunked && nextAction && (
        <div
          className="rounded-[var(--radius-xs)] border px-4 py-3 flex items-start gap-3"
          style={{ background: "var(--a-soft)", borderColor: "rgba(91,80,240,0.2)" }}
        >
          <span style={{ color: "var(--a-soft-fg)", marginTop: 2, flexShrink: 0 }}>→</span>
          <div>
            <p className="text-sm font-semibold" style={{ color: "var(--a-700)" }}>{nextAction.label}</p>
            <p className="text-xs mt-0.5" style={{ color: "var(--a-soft-fg)" }}>{nextAction.hint}</p>
          </div>
        </div>
      )}
      {isChunked && (
        <div
          className="rounded-[var(--radius-xs)] border px-4 py-3 flex items-center gap-3"
          style={{ background: "#e4f7ec", borderColor: "#c5edd4" }}
        >
          <span style={{ color: "#137a45", fontWeight: 700, flexShrink: 0 }}>✓</span>
          <div>
            <p className="text-sm font-semibold" style={{ color: "#0f5e35" }}>Pipeline complete</p>
            <p className="text-xs mt-0.5" style={{ color: "#137a45" }}>Use the panels below to search, ask questions, or prepare LLM payloads.</p>
          </div>
        </div>
      )}

      {/* Overview */}
      <Card title="Overview">
        <Row label="Status" value={<Badge label={doc.status} color={STATUS_BADGE[doc.status] ?? "bg-gray-100 text-gray-600"} />} />
        <Row label="Phase" value={<Badge label={phase} color="bg-indigo-100 text-indigo-700" />} />
        <Row label="Size" value={formatBytes(doc.file_size_bytes)} />
        {doc.mime_type && <Row label="MIME type" value={<span className="font-mono">{doc.mime_type}</span>} />}
        <Row label="Uploaded" value={formatDate(doc.created_at)} />
        <Row label="Last updated" value={formatDate(doc.updated_at)} />
      </Card>

      {/* Profile section */}
      {profile ? (
        <ProfileCard profile={profile} />
      ) : doc.profile ? (
        <Card title="Document Profile">
          <Row label="Detected type" value={doc.profile.detected_type ?? "—"} />
          {doc.profile.page_count != null && <Row label="Pages" value={String(doc.profile.page_count)} />}
          <Row label="Requires OCR" value={doc.profile.requires_ocr ? "Yes" : "No"} />
          <ActionButton onClick={handleProfile} loading={false} label="Re-run Profile" loadingLabel="Profiling…" variant="secondary" />
        </Card>
      ) : (
        <Card title="Document Profile">
          <p className="text-xs text-gray-400">Profile this document to detect its type and properties.</p>
          {profileState === "error" && (
            <p className="text-xs text-red-600">Profiling failed. Check the file and retry.</p>
          )}
          <ActionButton onClick={handleProfile} loading={profileState === "loading"} label="Profile Document" loadingLabel="Profiling…" />
        </Card>
      )}

      {/* Pipeline decision section */}
      {pipeline ? (
        <PipelineCard decision={pipeline} />
      ) : doc.pipeline ? (
        <Card title="Pipeline Decision">
          <Row label="Selected pipeline" value={<span className="font-semibold text-indigo-700">{doc.pipeline.selected_pipeline}</span>} />
          {doc.pipeline.output_format && <Row label="Output format" value={<span className="font-mono">{doc.pipeline.output_format}</span>} />}
          <ActionButton onClick={handlePipeline} loading={false} label="Re-run Pipeline Selection" loadingLabel="Selecting…" variant="secondary" />
        </Card>
      ) : doc.profile || profile ? (
        <Card title="Pipeline Decision">
          <p className="text-xs text-gray-400">Select the processing pipeline for this document type.</p>
          {pipelineState === "error" && (
            <p className="text-xs text-red-600">Pipeline selection failed.</p>
          )}
          <ActionButton onClick={handlePipeline} loading={pipelineState === "loading"} label="Select Pipeline" loadingLabel="Selecting…" />
        </Card>
      ) : null}

      {/* Conversion section */}
      {conversion ? (
        <>
          <ConversionCard conversion={conversion} />
          <div className="grid grid-cols-2 gap-2">
            <ActionButton onClick={handleConvert} loading={conversionState === "loading" && !conversionJob} label="Re-convert" loadingLabel="Converting…" variant="secondary" />
            <ActionButton onClick={handleConvertJob} loading={!!conversionJob && !isTerminalJob(conversionJob)} label="Run Convert Job" loadingLabel="Queued…" variant="secondary" />
          </div>
          <JobProgress job={conversionJob} onCancel={handleCancelConversionJob} />
        </>
      ) : doc.pipeline || pipeline ? (
        <Card title="Conversion">
          <p className="text-xs text-gray-400">Convert the document to Markdown for chunking.</p>
          {conversionState === "error" && (
            <p className="text-xs text-red-600">Conversion failed. Check that the file is intact.</p>
          )}
          <div className="grid grid-cols-2 gap-2">
            <ActionButton onClick={handleConvert} loading={conversionState === "loading" && !conversionJob} label="Convert" loadingLabel="Converting…" />
            <ActionButton onClick={handleConvertJob} loading={!!conversionJob && !isTerminalJob(conversionJob)} label="Convert Job" loadingLabel="Queued…" variant="secondary" />
          </div>
          <JobProgress job={conversionJob} onCancel={handleCancelConversionJob} />
        </Card>
      ) : null}

      {/* Chunking section */}
      {chunking ? (
        <>
          <ChunksCard data={chunking} />
          <div className="grid grid-cols-2 gap-2">
            <ActionButton onClick={handleChunk} loading={chunkState === "loading" && !chunkJob} label="Re-chunk" loadingLabel="Chunking…" variant="secondary" />
            <ActionButton onClick={handleChunkJob} loading={!!chunkJob && !isTerminalJob(chunkJob)} label="Run Chunk Job" loadingLabel="Queued…" variant="secondary" />
          </div>
          <JobProgress job={chunkJob} onCancel={handleCancelChunkJob} />
        </>
      ) : conversion ? (
        <Card title="Chunking">
          <p className="text-xs text-gray-400">Split the document into chunks for search and LLM queries.</p>
          {chunkState === "error" && (
            <p className="text-xs text-red-600">Chunking failed.</p>
          )}
          <div className="grid grid-cols-2 gap-2">
            <ActionButton onClick={handleChunk} loading={chunkState === "loading" && !chunkJob} label="Generate" loadingLabel="Chunking…" />
            <ActionButton onClick={handleChunkJob} loading={!!chunkJob && !isTerminalJob(chunkJob)} label="Chunk Job" loadingLabel="Queued…" variant="secondary" />
          </div>
          <JobProgress job={chunkJob} onCancel={handleCancelChunkJob} />
        </Card>
      ) : null}

      {/* Document preview — available after conversion */}
      {(conversion || conversionState === "success" || doc.conversion) && (
        <PreviewPanel documentId={documentId} />
      )}

      {/* Integrity check — available after upload */}
      {integrity ? (
        <>
          <IntegrityCard report={integrity} />
          <ActionButton onClick={handleIntegrity} loading={integrityState === "loading"} label="Re-check Integrity" loadingLabel="Checking…" variant="secondary" />
        </>
      ) : (
        <Card title="Integrity Check">
          <p className="text-xs text-gray-400">Verify file integrity, chunk hashes, and conversion quality.</p>
          {integrityState === "error" && (
            <p className="text-xs text-red-600">Integrity check failed to run.</p>
          )}
          <ActionButton onClick={handleIntegrity} loading={integrityState === "loading"} label="Check Integrity" loadingLabel="Checking…" variant="secondary" />
        </Card>
      )}

      {/* Export panel — available once any artifact exists */}
      {(doc.profile || profile || doc.pipeline || pipeline || conversion || doc.conversion) && (
        <ExportPanel
          documentId={documentId}
          hasProfile={!!(doc.profile || profile)}
          hasPipeline={!!(doc.pipeline || pipeline)}
          hasConversion={!!(conversion || doc.conversion)}
          hasChunks={!!(chunking || doc.chunks)}
        />
      )}

      <JobHistoryPanel documentId={documentId} />

      {/* Interactive panels — available after chunking */}
      {isChunked && (
        <>
          <IndexPanel documentId={documentId} isIndexed={isIndexed} onIndexed={(v) => setIsIndexed(v)} />
          <SearchPanel documentId={documentId} isIndexed={isIndexed} />
          <EvaluationPanel documentId={documentId} isIndexed={isIndexed} />
          <AskPanel documentId={documentId} isIndexed={isIndexed} localOnlyMode={localOnlyMode} />
          <LLMPayloadPanel documentId={documentId} />
          <TokenBudgetPanel documentId={documentId} />
          <SecurityPanel documentId={documentId} />
          <ProjectPanel
            currentDocumentId={documentId}
            currentDocumentName={doc.original_filename}
          />
        </>
      )}

      {/* Audit timeline */}
      <AuditTimeline events={auditEvents} />
    </main>
  );
}
