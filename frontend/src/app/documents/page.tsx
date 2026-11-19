"use client";

import { useEffect, useState } from "react";
import { exportDocumentsCsv, listDocumentsPaginated, type DocumentListItem } from "@/lib/api";

const PHASE_COLORS: Record<string, { bg: string; text: string }> = {
  upload:           { bg: "#eef0f4", text: "#4a5568" },
  profiled:         { bg: "#e8f0ff", text: "#1d59c7" },
  pipeline_decided: { bg: "#efedfe", text: "#4a3fe0" },
  converted:        { bg: "#fdf0d9", text: "#97600d" },
  chunked:          { bg: "#e4f7ec", text: "#137a45" },
};

const CAT_COLORS: Record<string, { bg: string; text: string }> = {
  pdf:      { bg: "#fde8e6", text: "#c2382b" },
  docx:     { bg: "#e8f0ff", text: "#1d59c7" },
  pptx:     { bg: "#fdeada", text: "#b35713" },
  xlsx:     { bg: "#e4f7ec", text: "#137a45" },
  csv:      { bg: "#def6ea", text: "#07835a" },
  txt:      { bg: "#eef0f4", text: "#4a5568" },
  markdown: { bg: "#eef0f4", text: "#4a5568" },
  html:     { bg: "#fdf0d9", text: "#97600d" },
  image:    { bg: "#f0e9fe", text: "#6d3fd1" },
  unknown:  { bg: "#eef0f4", text: "#4a5568" },
};

const PHASES = ["", "upload", "profiled", "pipeline_decided", "converted", "chunked"];
const PAGE_SIZE = 20;

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

function getMimeCategory(mime?: string): string {
  if (!mime) return "unknown";
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("word") || mime.includes("docx")) return "docx";
  if (mime.includes("presentation") || mime.includes("pptx")) return "pptx";
  if (mime.includes("sheet") || mime.includes("xlsx")) return "xlsx";
  if (mime.includes("csv")) return "csv";
  if (mime.includes("text/plain")) return "txt";
  if (mime.includes("markdown")) return "markdown";
  if (mime.includes("html")) return "html";
  if (mime.includes("image")) return "image";
  return "unknown";
}

export default function DocumentsPage() {
  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [loadedQuery, setLoadedQuery] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [phaseFilter, setPhaseFilter] = useState("");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [csvExporting, setCsvExporting] = useState(false);

  const queryKey = JSON.stringify([page, search, phaseFilter, sortOrder]);
  const loading = loadedQuery !== queryKey;

  useEffect(() => {
    let stale = false;
    listDocumentsPaginated({ page, page_size: PAGE_SIZE, search, phase: phaseFilter, sort: sortOrder })
      .then((data) => {
        if (stale) return;
        setItems(data.documents);
        setTotal(data.total);
        setPages(data.pages);
        setError(null);
        setLoadedQuery(queryKey);
      })
      .catch((err) => {
        if (stale) return;
        setError(err instanceof Error ? err.message : "Failed to load documents");
        setLoadedQuery(queryKey);
      });
    return () => { stale = true; };
  }, [page, search, phaseFilter, sortOrder, queryKey]);

  const handleSearch = () => { setSearch(searchInput); setPage(1); };
  const handlePhaseChange = (v: string) => { setPhaseFilter(v); setPage(1); };
  const handleSortChange = (v: "newest" | "oldest") => { setSortOrder(v); setPage(1); };

  const handleExportCsv = async () => {
    setCsvExporting(true);
    try {
      await exportDocumentsCsv({ search, phase: phaseFilter, sort: sortOrder });
    } catch { /* silently fail */ } finally {
      setCsvExporting(false);
    }
  };

  const inputStyle = {
    background: "var(--surface)",
    border: "1px solid var(--border-2)",
    borderRadius: "var(--radius-xs)",
    color: "var(--text)",
    fontSize: "0.85rem",
    padding: "8px 12px",
    outline: "none",
    width: "100%",
  } as React.CSSProperties;

  return (
    <main className="max-w-4xl mx-auto px-8 py-8 space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.09em] mb-2" style={{ color: "var(--text-3)" }}>
            Library
          </p>
          <h1 className="text-[2.1rem] font-bold tracking-[-0.025em] leading-none" style={{ color: "var(--text)" }}>
            Documents
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--text-2)" }}>
            {total > 0 ? `${total} document${total !== 1 ? "s" : ""} in your local workspace` : "All uploaded documents."}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleExportCsv}
            disabled={csvExporting}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border-2)",
              color: csvExporting ? "var(--text-3)" : "var(--text)",
            }}
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
              <path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5"/><path d="M5 18h14"/>
            </svg>
            {csvExporting ? "Exporting…" : "Export CSV"}
          </button>
          <a
            href="/upload"
            className="btn-grad inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-xs)] text-sm font-semibold"
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            Upload
          </a>
        </div>
      </div>

      {/* Filter bar */}
      <div
        className="rounded-[var(--radius)] p-4 flex flex-wrap gap-2 items-center"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--card-shadow)" }}
      >
        <div className="relative flex-1 min-w-[200px]">
          <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-3)" }}>
            <circle cx="11" cy="11" r="7"/><path d="M20 20l-3.2-3.2"/>
          </svg>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search by filename…"
            style={{ ...inputStyle, paddingLeft: 34 }}
          />
        </div>
        <select
          value={phaseFilter}
          onChange={(e) => handlePhaseChange(e.target.value)}
          style={{ ...inputStyle, width: "auto", minWidth: 150, cursor: "pointer" }}
        >
          {PHASES.map((p) => (
            <option key={p} value={p}>{p === "" ? "All phases" : p}</option>
          ))}
        </select>
        <select
          value={sortOrder}
          onChange={(e) => handleSortChange(e.target.value as "newest" | "oldest")}
          style={{ ...inputStyle, width: "auto", cursor: "pointer" }}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </select>
        <button
          onClick={handleSearch}
          className="btn-grad px-4 py-2 rounded-[var(--radius-xs)] text-sm font-semibold"
        >
          Search
        </button>
      </div>

      {loading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="rounded-[var(--radius)] p-4 animate-pulse h-[72px]"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            />
          ))}
        </div>
      )}

      {error && (
        <div
          className="rounded-[var(--radius-xs)] border px-4 py-3 text-sm"
          style={{ background: "#fde8e6", borderColor: "#f7cbc6", color: "#c2382b" }}
        >
          {error}
        </div>
      )}

      {!loading && !error && total === 0 && !search && !phaseFilter && (
        <div
          className="rounded-[var(--radius)] px-6 py-16 text-center"
          style={{ border: "2px dashed var(--border-2)" }}
        >
          <p className="text-sm font-medium" style={{ color: "var(--text-2)" }}>No documents yet</p>
          <p className="text-xs mt-1 mb-5" style={{ color: "var(--text-3)" }}>Upload a file to get started.</p>
          <a href="/upload" className="btn-grad inline-flex px-4 py-2 rounded-[var(--radius-xs)] text-sm font-semibold">
            Upload a document
          </a>
        </div>
      )}

      {!loading && !error && items.length === 0 && (search || phaseFilter) && (
        <div
          className="rounded-[var(--radius)] px-6 py-10 text-center text-sm"
          style={{ border: "2px dashed var(--border-2)", color: "var(--text-3)" }}
        >
          No documents match your filters.
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className="space-y-2">
            {items.map((doc) => {
              const phase = PHASE_COLORS[doc.current_phase] ?? PHASE_COLORS.upload;
              const cat = getMimeCategory(doc.mime_type ?? "");
              const catColor = CAT_COLORS[cat] ?? CAT_COLORS.unknown;
              const label = cat.toUpperCase().slice(0, 4);
              return (
                <a
                  key={doc.document_id}
                  href={`/documents/${doc.document_id}`}
                  className="hoverrow flex items-center gap-4 rounded-[var(--radius)] p-4 transition-all"
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    boxShadow: "var(--card-shadow)",
                    display: "flex",
                  }}
                >
                  <span
                    className="w-[42px] h-[42px] rounded-[11px] flex items-center justify-center shrink-0"
                    style={{ background: catColor.bg, color: catColor.text }}
                  >
                    <span className="font-mono text-[10px] font-bold tracking-wider">{label}</span>
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[0.9rem] font-semibold truncate" style={{ color: "var(--text)" }}>
                      {doc.original_filename}
                    </p>
                    <p className="text-xs font-mono truncate mt-0.5" style={{ color: "var(--text-3)" }}>
                      {doc.document_id}
                    </p>
                    <div className="flex flex-wrap gap-3 mt-1.5 text-xs" style={{ color: "var(--text-3)" }}>
                      <span>{formatBytes(doc.file_size_bytes)}</span>
                      {doc.mime_type && <span className="font-mono">{doc.mime_type.split("/").pop()}</span>}
                      <span>{formatDate(doc.created_at)}</span>
                    </div>
                  </div>
                  <span
                    className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap shrink-0"
                    style={{ background: phase.bg, color: phase.text }}
                  >
                    {doc.current_phase}
                  </span>
                  <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" style={{ color: "var(--text-3)", flexShrink: 0 }}>
                    <path d="M9 6l6 6-6 6"/>
                  </svg>
                </a>
              );
            })}
          </div>

          {/* Pagination */}
          {pages > 1 && (
            <div className="flex items-center justify-between gap-4">
              <p className="text-xs" style={{ color: "var(--text-3)" }}>
                Page {page} of {pages} · {total} total
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1.5 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
                  style={{ color: page === 1 ? "var(--text-3)" : "var(--text-2)" }}
                >
                  ← Prev
                </button>
                {Array.from({ length: Math.min(5, pages) }, (_, i) => {
                  const start = Math.max(1, Math.min(page - 2, pages - 4));
                  const p = start + i;
                  return (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className="w-8 h-8 rounded-[var(--radius-xs)] text-sm font-medium transition-all"
                      style={
                        p === page
                          ? { background: "linear-gradient(135deg, #7a4ff7, #3f6bf6)", color: "#fff", boxShadow: "0 4px 12px -5px rgba(91,80,240,0.6)" }
                          : { color: "var(--text-2)" }
                      }
                    >
                      {p}
                    </button>
                  );
                })}
                <button
                  onClick={() => setPage((p) => Math.min(pages, p + 1))}
                  disabled={page === pages}
                  className="px-3 py-1.5 rounded-[var(--radius-xs)] text-sm font-medium transition-colors"
                  style={{ color: page === pages ? "var(--text-3)" : "var(--text-2)" }}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
}
