"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchDashboardStats,
  fetchHealth,
  listDocuments,
  listRecentAudit,
  type AuditEventItem,
  type DashboardStats,
  type DocumentListItem,
  type HealthStatus,
} from "@/lib/api";

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

const PHASE_COLORS: Record<string, { bg: string; text: string }> = {
  upload:           { bg: "#eef0f4", text: "#4a5568" },
  profiled:         { bg: "#e8f0ff", text: "#1d59c7" },
  pipeline_decided: { bg: "#efedfe", text: "#4a3fe0" },
  converted:        { bg: "#fdf0d9", text: "#97600d" },
  chunked:          { bg: "#e4f7ec", text: "#137a45" },
};

const EVENT_COLORS: Record<string, { bg: string; text: string }> = {
  upload:    { bg: "#e8f0ff", text: "#1d59c7" },
  profile:   { bg: "#efedfe", text: "#4a3fe0" },
  pipeline:  { bg: "#f0e9fe", text: "#6d3fd1" },
  convert:   { bg: "#fdf0d9", text: "#97600d" },
  chunk:     { bg: "#e4f7ec", text: "#137a45" },
  integrity: { bg: "#def5f4", text: "#0a7d80" },
  llm_call:  { bg: "#def6ea", text: "#07835a" },
  security:  { bg: "#eef0f4", text: "#4a5568" },
};

function PhaseBadge({ phase }: { phase: string }) {
  const c = PHASE_COLORS[phase] ?? { bg: "#eef0f4", text: "#4a5568" };
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap"
      style={{ background: c.bg, color: c.text }}
    >
      {phase}
    </span>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: number | string;
  sub?: string;
  icon: string;
}) {
  const iconPaths: Record<string, string> = {
    documents: '<path d="M8 3h6l5 5v11a2 2 0 01-2 2H8a2 2 0 01-2-2V5a2 2 0 012-2z"/><path d="M14 3v5h5"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/>',
    spinner: '<path d="M20 11a8 8 0 00-14-4.5L4 8"/><path d="M4 4v4h4"/>',
    folder: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
  };
  return (
    <div
      className="rounded-[var(--radius)] p-5 transition-all duration-150"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        boxShadow: "var(--card-shadow)",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <p
          className="text-[11px] font-semibold uppercase tracking-[0.08em]"
          style={{ color: "var(--text-3)" }}
        >
          {label}
        </p>
        <span
          className="w-[30px] h-[30px] rounded-[9px] flex items-center justify-center shrink-0"
          style={{ background: "var(--a-soft)", color: "var(--a-soft-fg)" }}
        >
          <svg
            width={15}
            height={15}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            dangerouslySetInnerHTML={{ __html: iconPaths[icon] ?? "" }}
          />
        </span>
      </div>
      <p
        className="text-[2.2rem] font-bold mt-3 mb-1 leading-none tracking-tight"
        style={{ color: "var(--text)" }}
      >
        {value}
      </p>
      {sub && (
        <p className="text-xs" style={{ color: "var(--text-3)" }}>
          {sub}
        </p>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchDashboardStats().catch(() => null),
      listDocuments().catch(() => null),
      listRecentAudit(10).catch(() => null),
      fetchHealth().catch(() => null),
    ]).then(([s, d, e, h]) => {
      if (s) setStats(s);
      if (d) setDocs(d.documents.slice(0, 6));
      if (e) setEvents(e.events.slice(0, 8));
      if (h) setHealth(h);
      setLoading(false);
    });
  }, []);

  return (
    <main className="max-w-5xl mx-auto px-8 py-8 space-y-7 fade-in">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p
            className="text-[11px] font-semibold uppercase tracking-[0.09em] mb-2"
            style={{ color: "var(--text-3)" }}
          >
            Overview
          </p>
          <h1
            className="text-[2.1rem] font-bold tracking-[-0.025em] leading-none"
            style={{ color: "var(--text)" }}
          >
            Dashboard
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--text-2)" }}>
            Everything running locally — no document leaves this machine.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {health && (
            <span
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold"
              style={{ background: "#e4f7ec", color: "#137a45" }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              Backend online
            </span>
          )}
          {health?.local_only_mode && (
            <span
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold"
              style={{ background: "#e2f4fd", color: "#1372a6" }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
              Local-only
            </span>
          )}
          <a
            href="/upload"
            className="btn-grad inline-flex items-center gap-2 px-4 py-2 rounded-[var(--radius-xs)] text-sm font-semibold transition-all"
          >
            <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4"/><path d="M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2"/>
            </svg>
            Upload
          </a>
        </div>
      </div>

      {/* Stats */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="rounded-[var(--radius)] p-5 animate-pulse h-28"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Documents" value={stats?.total_documents ?? 0} sub="total uploaded" icon="documents" />
          <StatCard label="Completed" value={stats?.completed_documents ?? 0} sub="fully chunked" icon="check" />
          <StatCard label="In Progress" value={stats?.documents_in_progress ?? 0} sub="pipeline running" icon="spinner" />
          <StatCard label="Projects" value={stats?.total_projects ?? 0} sub="document groups" icon="folder" />
        </div>
      )}

      {/* Recent docs + Activity */}
      <div className="grid md:grid-cols-2 gap-5">
        {/* Recent Documents */}
        <div
          className="rounded-[var(--radius)] overflow-hidden"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            boxShadow: "var(--card-shadow)",
          }}
        >
          <div
            className="px-5 py-3.5 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="text-sm font-[640] tracking-tight" style={{ color: "var(--text)" }}>
              Recent Documents
            </h2>
            <Link
              href="/documents"
              className="text-xs font-medium flex items-center gap-1"
              style={{ color: "var(--a-soft-fg)" }}
            >
              View all
              <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                <path d="M5 12h14m0 0l-6-6m6 6l-6 6"/>
              </svg>
            </Link>
          </div>
          {docs.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm" style={{ color: "var(--text-3)" }}>
              No documents yet.{" "}
              <a href="/upload" style={{ color: "var(--a-soft-fg)" }} className="font-medium">
                Upload one
              </a>{" "}
              to start.
            </div>
          ) : (
            <ul>
              {docs.map((doc) => (
                <li key={doc.document_id}>
                  <a
                    href={`/documents/${doc.document_id}`}
                    className="hoverrow flex items-center justify-between gap-3 px-5 py-3 border-b last:border-0"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>
                        {doc.original_filename}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--text-3)" }}>
                        {formatBytes(doc.file_size_bytes)} · {formatDate(doc.created_at)}
                      </p>
                    </div>
                    <PhaseBadge phase={doc.current_phase} />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recent Activity */}
        <div
          className="rounded-[var(--radius)] overflow-hidden"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            boxShadow: "var(--card-shadow)",
          }}
        >
          <div
            className="px-5 py-3.5 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="text-sm font-[640] tracking-tight" style={{ color: "var(--text)" }}>
              Recent Activity
            </h2>
            <a
              href="/activity"
              className="text-xs font-medium flex items-center gap-1"
              style={{ color: "var(--a-soft-fg)" }}
            >
              View all
              <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                <path d="M5 12h14m0 0l-6-6m6 6l-6 6"/>
              </svg>
            </a>
          </div>
          {events.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm" style={{ color: "var(--text-3)" }}>
              No activity yet.
            </div>
          ) : (
            <ul>
              {events.map((e) => {
                const c = EVENT_COLORS[e.event_type] ?? { bg: "#eef0f4", text: "#4a5568" };
                return (
                  <li
                    key={e.id}
                    className="flex items-center gap-3 px-5 py-2.5 border-b last:border-0"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <span
                      className="px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap shrink-0"
                      style={{ background: c.bg, color: c.text }}
                    >
                      {e.event_type}
                    </span>
                    <span className="text-xs truncate font-mono" style={{ color: "var(--text-3)" }}>
                      {e.document_id ? `doc:${e.document_id.slice(0, 12)}…` : e.project_id ? `proj:${e.project_id.slice(0, 12)}…` : "—"}
                    </span>
                    <span className="text-xs shrink-0 ml-auto" style={{ color: "var(--text-3)" }}>
                      {new Date(e.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* CTA banner */}
      <div className="cta-banner p-8 flex items-center justify-between gap-6 flex-wrap">
        <div className="relative z-10">
          <div
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold mb-4"
            style={{ background: "rgba(255,255,255,0.16)", color: "#fff" }}
          >
            <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>
            </svg>
            100% local processing
          </div>
          <h2 className="text-[1.5rem] font-bold text-white tracking-tight leading-tight">
            Ready to analyze a document?
          </h2>
          <p className="text-sm mt-2 max-w-sm" style={{ color: "rgba(255,255,255,0.82)" }}>
            Upload PDFs, Word docs, spreadsheets, slides, markdown, or images. Profiling starts instantly.
          </p>
        </div>
        <div className="relative z-10 shrink-0">
          <a
            href="/upload"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[var(--radius-xs)] text-sm font-semibold transition-all"
            style={{ background: "#fff", color: "var(--a-700)" }}
          >
            <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4"/><path d="M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2"/>
            </svg>
            Upload a document
          </a>
        </div>
      </div>
    </main>
  );
}
