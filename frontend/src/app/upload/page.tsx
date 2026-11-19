import { UploadZone } from "@/components/UploadZone";

const FORMATS = [
  { t: "PDF",      c: "#fde8e6", fg: "#c2382b" },
  { t: "DOCX",     c: "#e8f0ff", fg: "#1d59c7" },
  { t: "PPTX",     c: "#fdeada", fg: "#b35713" },
  { t: "XLSX",     c: "#e4f7ec", fg: "#137a45" },
  { t: "CSV",      c: "#def6ea", fg: "#07835a" },
  { t: "TXT",      c: "#eef0f4", fg: "#4a5568" },
  { t: "Markdown", c: "#eef0f4", fg: "#4a5568" },
  { t: "HTML",     c: "#fdf0d9", fg: "#97600d" },
  { t: "PNG",      c: "#f0e9fe", fg: "#6d3fd1" },
  { t: "JPG",      c: "#f0e9fe", fg: "#6d3fd1" },
  { t: "WEBP",     c: "#f0e9fe", fg: "#6d3fd1" },
];

const STEPS = [
  { icon: "search",  n: "01", t: "Profile",       d: "Detect type, text layer & OCR need" },
  { icon: "branch",  n: "02", t: "Decide",         d: "Pick the optimal conversion pipeline" },
  { icon: "layers",  n: "03", t: "Chunk & Index",  d: "Split, embed & make searchable" },
];

const STEP_ICONS: Record<string, string> = {
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.2-3.2"/>',
  branch: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="8" r="2.5"/><path d="M6 8.5v7M8.5 8h4a3 3 0 013 3v0"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
};

export default function UploadPage() {
  return (
    <main className="max-w-2xl mx-auto px-8 py-8 space-y-7 fade-in">
      {/* Header */}
      <div>
        <p
          className="text-[11px] font-semibold uppercase tracking-[0.09em] mb-2"
          style={{ color: "var(--text-3)" }}
        >
          Ingest
        </p>
        <h1
          className="text-[2.1rem] font-bold tracking-[-0.025em] leading-none"
          style={{ color: "var(--text)" }}
        >
          Upload Document
        </h1>
        <p className="text-sm mt-2" style={{ color: "var(--text-2)" }}>
          Drop a file to start the analysis pipeline. You&apos;ll be taken to its detail page automatically.
        </p>
      </div>

      <UploadZone />

      {/* Supported formats */}
      <div
        className="rounded-[var(--radius)] overflow-hidden"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          boxShadow: "var(--card-shadow)",
        }}
      >
        <div
          className="px-5 py-3.5 flex items-center gap-2"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" style={{ color: "var(--a-soft-fg)" }}>
            <path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>
          </svg>
          <h2 className="text-sm font-[640] tracking-tight" style={{ color: "var(--text)" }}>
            Supported Formats
          </h2>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex flex-wrap gap-2">
            {FORMATS.map((f) => (
              <span
                key={f.t}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-[9px] text-[13px] font-[580]"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: f.fg }}
                />
                {f.t}
              </span>
            ))}
          </div>
          <div
            className="flex gap-2.5 items-start rounded-[var(--radius-sm)] p-3"
            style={{ background: "var(--inset)", border: "1px solid var(--border)" }}
          >
            <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" style={{ color: "var(--a-soft-fg)", flexShrink: 0, marginTop: 1 }}>
              <circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>
            </svg>
            <p className="text-xs leading-relaxed" style={{ color: "var(--text-2)" }}>
              Scanned PDFs and images are routed through local OCR automatically. Spreadsheets are flattened to structured summaries before chunking.
            </p>
          </div>
        </div>
      </div>

      {/* Pipeline steps */}
      <div className="grid grid-cols-3 gap-4">
        {STEPS.map((s) => (
          <div
            key={s.t}
            className="rounded-[var(--radius)] p-5 flex flex-col gap-3"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              boxShadow: "var(--card-shadow)",
            }}
          >
            <div className="flex items-center justify-between">
              <span
                className="w-[30px] h-[30px] rounded-[9px] flex items-center justify-center"
                style={{ background: "var(--a-soft)", color: "var(--a-soft-fg)" }}
              >
                <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" dangerouslySetInnerHTML={{ __html: STEP_ICONS[s.icon] ?? "" }} />
              </span>
              <span className="font-mono text-[11px]" style={{ color: "var(--text-3)" }}>{s.n}</span>
            </div>
            <div>
              <p className="text-sm font-[620]" style={{ color: "var(--text)" }}>{s.t}</p>
              <p className="text-xs mt-1 leading-relaxed" style={{ color: "var(--text-3)" }}>{s.d}</p>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
