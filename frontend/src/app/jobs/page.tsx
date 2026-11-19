"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  cancelJob,
  cleanupJobs,
  listJobs,
  retryJob,
  type JobDetail,
  type JobStatus,
} from "@/lib/api";

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  queued:    { bg: "#eef0f4", text: "#4a5568" },
  running:   { bg: "#efedfe", text: "#4a3fe0" },
  succeeded: { bg: "#e4f7ec", text: "#137a45" },
  failed:    { bg: "#fde8e6", text: "#c2382b" },
  canceled:  { bg: "#fdf0d9", text: "#97600d" },
};

const JOB_TYPES = ["all", "convert", "chunk", "index", "retrieval_evaluation", "grounded_answer"];
const STATUSES: Array<JobStatus | "all"> = ["all", "queued", "running", "succeeded", "failed", "canceled"];

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] ?? STATUS_COLORS.queued;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap"
      style={{ background: c.bg, color: c.text }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: c.text }} />
      {status}
    </span>
  );
}

const selectStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border-2)",
  borderRadius: "var(--radius-xs)",
  color: "var(--text)",
  fontSize: "0.82rem",
  padding: "7px 10px",
  outline: "none",
  cursor: "pointer",
} as React.CSSProperties;

function JobsPageContent() {
  const searchParams = useSearchParams();
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [total, setTotal] = useState(0);
  const [loadedQuery, setLoadedQuery] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | "all">("all");
  const [jobType, setJobType] = useState("all");
  const [documentId, setDocumentId] = useState(() => searchParams.get("document_id") ?? "");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);

  const limit = 25;

  const queryKey = JSON.stringify([documentId, status, jobType, sort, offset, refreshCount]);
  const loading = loadedQuery !== queryKey;

  useEffect(() => {
    let stale = false;
    listJobs({
      documentId: documentId.trim() || undefined,
      status,
      jobType,
      sort,
      limit,
      offset,
    })
      .then((data) => {
        if (stale) return;
        setJobs(data.jobs);
        setTotal(data.total);
        setError(null);
        setLoadedQuery(queryKey);
      })
      .catch((err) => {
        if (stale) return;
        setError(err instanceof Error ? err.message : "Failed to load jobs");
        setLoadedQuery(queryKey);
      });
    return () => { stale = true; };
  }, [documentId, status, jobType, sort, offset, refreshCount, queryKey]);

  const refreshJobs = () => setRefreshCount((c) => c + 1);

  const pageLabel = useMemo(() => {
    if (total === 0) return "0 jobs";
    return `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`;
  }, [offset, total]);

  const handleRetry = async (jobId: string) => {
    setActionBusy(jobId);
    setError(null);
    try {
      await retryJob(jobId);
      refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setActionBusy(null);
    }
  };

  const handleCancel = async (jobId: string) => {
    setActionBusy(jobId);
    setError(null);
    try {
      await cancelJob(jobId);
      refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setActionBusy(null);
    }
  };

  const handleCleanup = async () => {
    setActionBusy("cleanup");
    setCleanupMessage(null);
    setError(null);
    try {
      const result = await cleanupJobs({ older_than_days: 30, statuses: ["succeeded", "failed", "canceled"] });
      setCleanupMessage(`Deleted ${result.deleted_count} old job record(s).`);
      refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cleanup failed");
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <main className="max-w-5xl mx-auto px-8 py-8 space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.09em] mb-2" style={{ color: "var(--text-3)" }}>
            Operations
          </p>
          <h1 className="text-[2.1rem] font-bold tracking-[-0.025em] leading-none" style={{ color: "var(--text)" }}>
            Jobs
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--text-2)" }}>
            Background job history, retry, and operational status.
          </p>
        </div>
        <button
          onClick={handleCleanup}
          disabled={actionBusy === "cleanup"}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
          style={{ background: "var(--surface)", border: "1px solid var(--border-2)", color: actionBusy === "cleanup" ? "var(--text-3)" : "var(--text)" }}
        >
          {actionBusy === "cleanup" ? "Cleaning…" : "Cleanup 30d"}
        </button>
      </div>

      {/* Filter bar */}
      <div
        className="rounded-[var(--radius)] p-4 flex flex-wrap gap-2 items-center"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--card-shadow)" }}
      >
        <select value={status} onChange={(e) => { setStatus(e.target.value as JobStatus | "all"); setOffset(0); }} style={selectStyle}>
          {STATUSES.map((item) => <option key={item} value={item}>{item === "all" ? "All statuses" : item}</option>)}
        </select>
        <select value={jobType} onChange={(e) => { setJobType(e.target.value); setOffset(0); }} style={selectStyle}>
          {JOB_TYPES.map((item) => <option key={item} value={item}>{item === "all" ? "All job types" : item}</option>)}
        </select>
        <input
          value={documentId}
          onChange={(e) => { setDocumentId(e.target.value); setOffset(0); }}
          placeholder="document_id"
          className="flex-1 min-w-[160px] font-mono text-[0.8rem]"
          style={{ ...selectStyle, cursor: "text", width: "auto" }}
        />
        <select value={sort} onChange={(e) => { setSort(e.target.value as "newest" | "oldest"); setOffset(0); }} style={selectStyle}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </select>
        <button
          onClick={refreshJobs}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
          style={{ background: "var(--surface-2)", border: "1px solid var(--border-2)", color: "var(--text-2)" }}
        >
          <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
            <path d="M20 11a8 8 0 00-14-4.5L4 8"/><path d="M4 4v4h4"/>
          </svg>
          Refresh
        </button>
        <span className="ml-auto text-xs" style={{ color: "var(--text-3)" }}>{pageLabel}</span>

        {cleanupMessage && (
          <p className="w-full text-xs" style={{ color: "#137a45" }}>{cleanupMessage}</p>
        )}
        {error && (
          <p className="w-full text-xs" style={{ color: "#c2382b" }}>{error}</p>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-20 rounded-[var(--radius)] animate-pulse"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div
          className="rounded-[var(--radius)] px-6 py-16 text-center text-sm"
          style={{ border: "2px dashed var(--border-2)", color: "var(--text-3)" }}
        >
          No jobs match the current filters.
        </div>
      ) : (
        <div
          className="rounded-[var(--radius)] overflow-hidden"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--card-shadow)" }}
        >
          {jobs.map((job, idx) => {
            const isExpanded = expanded === job.job_id;
            return (
              <div
                key={job.job_id}
                style={{ borderTop: idx === 0 ? "none" : "1px solid var(--border)" }}
              >
                <div className="px-5 py-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <StatusBadge status={job.status} />
                    <div className="min-w-0 flex-1">
                      <button
                        onClick={() => setExpanded(isExpanded ? null : job.job_id)}
                        className="flex items-center gap-1.5 text-left"
                        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}
                      >
                        <svg
                          width={13}
                          height={13}
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={2}
                          strokeLinecap="round"
                          style={{ color: "var(--text-3)", transform: isExpanded ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}
                        >
                          <path d="M9 6l6 6-6 6"/>
                        </svg>
                        <span className="font-mono text-sm font-[620]" style={{ color: "var(--text)" }}>
                          {job.job_type}
                        </span>
                      </button>
                      <p className="text-xs mt-1 truncate max-w-md" style={{ color: "var(--text-3)" }}>
                        {job.message ?? job.current_step ?? job.job_id}
                      </p>
                    </div>
                    <div className="hidden sm:block w-32 shrink-0">
                      <div
                        className="h-1.5 rounded-full overflow-hidden"
                        style={{ background: "var(--surface-3)" }}
                      >
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${job.progress_percent}%`,
                            background: job.status === "succeeded"
                              ? "#16a35a"
                              : job.status === "failed"
                              ? "#dc4436"
                              : "linear-gradient(90deg, #7a4ff7, #3f6bf6)",
                          }}
                        />
                      </div>
                      <p className="text-right text-[11px] mt-1" style={{ color: "var(--text-3)" }}>
                        {job.progress_percent}%
                      </p>
                    </div>
                    {job.document_id && (
                      <a
                        href={`/documents/${job.document_id}`}
                        className="hidden md:block text-xs font-medium"
                        style={{ color: "var(--a-soft-fg)" }}
                      >
                        Document
                      </a>
                    )}
                    {job.can_cancel && (
                      <button
                        onClick={() => handleCancel(job.job_id)}
                        disabled={actionBusy === job.job_id}
                        className="text-xs font-medium transition-colors"
                        style={{ color: "var(--text-3)", background: "none", border: "none", cursor: "pointer" }}
                      >
                        Cancel
                      </button>
                    )}
                    {job.can_retry && (
                      <button
                        onClick={() => handleRetry(job.job_id)}
                        disabled={actionBusy === job.job_id}
                        className="text-xs font-medium transition-colors"
                        style={{ color: "var(--a-soft-fg)", background: "none", border: "none", cursor: "pointer" }}
                      >
                        Retry
                      </button>
                    )}
                  </div>

                  {isExpanded && (
                    <div
                      className="rounded-[var(--radius-sm)] p-3.5 space-y-3 text-xs"
                      style={{ background: "var(--inset)", border: "1px solid var(--border)" }}
                    >
                      <div className="grid gap-2 sm:grid-cols-2">
                        <p><span style={{ color: "var(--text-3)" }}>Job ID</span> <span className="font-mono ml-1.5" style={{ color: "var(--text)" }}>{job.job_id}</span></p>
                        <p><span style={{ color: "var(--text-3)" }}>Retry of</span> <span className="ml-1.5" style={{ color: "var(--text)" }}>{job.retry_of_job_id ?? "—"}</span></p>
                        <p><span style={{ color: "var(--text-3)" }}>Created</span> <span className="ml-1.5" style={{ color: "var(--text)" }}>{formatDate(job.created_at)}</span></p>
                        <p><span style={{ color: "var(--text-3)" }}>Updated</span> <span className="ml-1.5" style={{ color: "var(--text)" }}>{formatDate(job.updated_at)}</span></p>
                      </div>
                      {job.error && (
                        <p
                          className="rounded-[var(--radius-xs)] px-3 py-2 flex gap-2"
                          style={{ background: "#fde8e6", border: "1px solid #f7cbc6", color: "#c2382b" }}
                        >
                          {job.error}
                        </p>
                      )}
                      {job.can_retry && (
                        <p style={{ color: "#97600d" }}>
                          This job can be retried. Retry creates a new job and keeps this record unchanged.
                        </p>
                      )}
                      {job.request && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-3)" }}>Request</p>
                          <pre
                            className="max-h-40 overflow-auto rounded-[var(--radius-xs)] p-2.5 text-[11px] leading-relaxed"
                            style={{ background: "#0c0a16", color: "#d6d3e6", border: "1px solid #1c1930" }}
                          >
                            {JSON.stringify(job.request, null, 2)}
                          </pre>
                        </div>
                      )}
                      {job.result && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-3)" }}>Result</p>
                          <pre
                            className="max-h-40 overflow-auto rounded-[var(--radius-xs)] p-2.5 text-[11px] leading-relaxed"
                            style={{ background: "#0c0a16", color: "#d6d3e6", border: "1px solid #1c1930" }}
                          >
                            {JSON.stringify(job.result, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex justify-between">
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
          style={{ background: "var(--surface)", border: "1px solid var(--border-2)", color: offset === 0 ? "var(--text-3)" : "var(--text-2)" }}
        >
          ← Previous
        </button>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={offset + limit >= total}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
          style={{ background: "var(--surface)", border: "1px solid var(--border-2)", color: offset + limit >= total ? "var(--text-3)" : "var(--text-2)" }}
        >
          Next →
        </button>
      </div>
    </main>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={null}>
      <JobsPageContent />
    </Suspense>
  );
}
