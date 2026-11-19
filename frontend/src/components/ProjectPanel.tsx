"use client";

import { useCallback, useState } from "react";
import {
  addDocumentToProject,
  askProject,
  createProject,
  searchProject,
  type Project,
  type ProjectAskResponse,
  type ProjectProvider,
  type ProjectSearchResponse,
  type ProjectSearchResultItem,
} from "@/lib/api";

type AsyncState = "idle" | "loading" | "success" | "error";

function Spinner({ className = "" }: { className?: string }) {
  return <div className={`border-2 border-t-transparent rounded-full animate-spin ${className}`} />;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
      {children}
    </p>
  );
}

const CONTENT_TYPE_COLORS: Record<string, string> = {
  text:  "bg-gray-100 text-gray-600",
  code:  "bg-violet-100 text-violet-700",
  table: "bg-teal-100 text-teal-700",
};

const PROJECT_PROVIDERS: { value: ProjectProvider; label: string }[] = [
  { value: "mock",   label: "Mock (no API key)" },
  { value: "claude", label: "Claude" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Gemini" },
];

// ── Search results list ───────────────────────────────────────────────────────

function ProjectSearchResults({ results }: { results: ProjectSearchResultItem[] }) {
  if (results.length === 0) {
    return <p className="text-xs text-gray-400">No results found for this query.</p>;
  }
  return (
    <div className="space-y-2">
      {results.map((item) => {
        const ctColor = CONTENT_TYPE_COLORS[item.content_type] ?? CONTENT_TYPE_COLORS.text;
        const breadcrumb = item.section_path.join(" › ") || "(root)";
        return (
          <div key={item.chunk_id} className="rounded-lg border border-gray-100 bg-white p-3 space-y-1.5">
            {/* Source document badge */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="px-1.5 py-0.5 rounded bg-rose-50 border border-rose-100 text-xs font-medium text-rose-700 truncate max-w-[180px]" title={item.source_filename}>
                {item.source_filename}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${ctColor}`}>
                {item.content_type}
              </span>
              <span className="text-xs font-mono text-indigo-600 ml-auto shrink-0">
                {item.score.toFixed(3)}
              </span>
              <span className="text-xs text-gray-400 shrink-0">~{item.estimated_tokens} tok</span>
            </div>
            <p className="text-xs text-gray-400 truncate">{breadcrumb}</p>
            <p className="text-xs text-gray-600 leading-relaxed line-clamp-3 font-mono whitespace-pre-wrap">
              {item.text_preview}
            </p>
            <p className="text-xs font-mono text-gray-300 truncate">{item.chunk_id.slice(0, 20)}…</p>
          </div>
        );
      })}
    </div>
  );
}

// ── Main ProjectPanel ─────────────────────────────────────────────────────────

interface ProjectPanelProps {
  currentDocumentId: string | null;
  currentDocumentName: string | null;
}

export function ProjectPanel({ currentDocumentId, currentDocumentName }: ProjectPanelProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [createState, setCreateState] = useState<AsyncState>("idle");
  const [projectName, setProjectName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const [addState, setAddState] = useState<AsyncState>("idle");
  const [addError, setAddError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchState, setSearchState] = useState<AsyncState>("idle");
  const [searchResp, setSearchResp] = useState<ProjectSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [askQuery, setAskQuery] = useState("");
  const [askProvider, setAskProvider] = useState<ProjectProvider>("mock");
  const [askState, setAskState] = useState<AsyncState>("idle");
  const [askResp, setAskResp] = useState<ProjectAskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const handleCreate = useCallback(async () => {
    if (!projectName.trim()) return;
    setCreateState("loading");
    setCreateError(null);
    try {
      const p = await createProject(projectName.trim());
      setProject(p);
      setProjectName("");
      setCreateState("success");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create project");
      setCreateState("error");
    }
  }, [projectName]);

  const handleAddDocument = useCallback(async () => {
    if (!project || !currentDocumentId) return;
    setAddState("loading");
    setAddError(null);
    try {
      const p = await addDocumentToProject(project.project_id, currentDocumentId);
      setProject(p);
      setAddState("success");
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add document");
      setAddState("error");
    }
  }, [project, currentDocumentId]);

  const handleSearch = useCallback(async () => {
    if (!project || !searchQuery.trim()) return;
    setSearchState("loading");
    setSearchResp(null);
    setSearchError(null);
    try {
      const resp = await searchProject(project.project_id, searchQuery.trim());
      setSearchResp(resp);
      setSearchState("success");
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed");
      setSearchState("error");
    }
  }, [project, searchQuery]);

  const handleAsk = useCallback(async () => {
    if (!project || !askQuery.trim()) return;
    setAskState("loading");
    setAskResp(null);
    setAskError(null);
    try {
      const resp = await askProject(project.project_id, askQuery.trim(), 10, askProvider);
      setAskResp(resp);
      setAskState("success");
    } catch (err) {
      setAskError(err instanceof Error ? err.message : "Ask failed");
      setAskState("error");
    }
  }, [project, askQuery, askProvider]);

  const handleSearchKey = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") handleSearch(); },
    [handleSearch],
  );
  const handleAskKey = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") handleAsk(); },
    [handleAsk],
  );

  const canAddCurrent =
    project !== null &&
    currentDocumentId !== null &&
    !project.document_ids.includes(currentDocumentId);

  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 space-y-4">
      <SectionLabel>Project Analyzer</SectionLabel>

      {/* ── Create project ── */}
      {!project && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">
            Group multiple documents into a project to search and ask across all of them.
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
              placeholder="Project name…"
              className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-rose-300"
            />
            <button
              onClick={handleCreate}
              disabled={!projectName.trim() || createState === "loading"}
              className={[
                "px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
                !projectName.trim() || createState === "loading"
                  ? "bg-gray-100 text-gray-400 cursor-default"
                  : "bg-rose-600 text-white hover:bg-rose-500",
              ].join(" ")}
            >
              {createState === "loading" ? <Spinner className="w-4 h-4 border-rose-200" /> : "Create"}
            </button>
          </div>
          {createState === "error" && createError && (
            <p className="text-xs text-red-600">{createError}</p>
          )}
        </div>
      )}

      {/* ── Project header ── */}
      {project && (
        <div className="rounded-lg border border-rose-200 bg-white p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-gray-900">{project.name}</p>
              <p className="text-xs font-mono text-gray-400 truncate">{project.project_id}</p>
            </div>
            <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-700 text-xs font-semibold">
              {project.document_ids.length} doc{project.document_ids.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* Document list */}
          {project.document_ids.length > 0 && (
            <div className="space-y-1">
              {project.document_ids.map((id) => (
                <div key={id} className="flex items-center gap-2 text-xs">
                  <span className="text-green-500 shrink-0">✓</span>
                  <span className="font-mono text-gray-500 truncate">{id.slice(0, 24)}…</span>
                </div>
              ))}
            </div>
          )}

          {/* Add current document */}
          {currentDocumentId && (
            <div className="pt-1 border-t border-gray-100">
              {canAddCurrent ? (
                <div className="space-y-1">
                  <p className="text-xs text-gray-500">
                    Add current document:{" "}
                    <span className="font-medium text-gray-700">{currentDocumentName}</span>
                  </p>
                  <button
                    onClick={handleAddDocument}
                    disabled={addState === "loading"}
                    className={[
                      "w-full py-1.5 rounded-lg text-xs font-semibold transition-colors",
                      addState === "loading"
                        ? "bg-gray-100 text-gray-400 cursor-default"
                        : "bg-rose-600 text-white hover:bg-rose-500",
                    ].join(" ")}
                  >
                    {addState === "loading" ? (
                      <span className="flex items-center justify-center gap-2">
                        <Spinner className="w-3 h-3 border-rose-200" /> Adding…
                      </span>
                    ) : (
                      "Add to Project"
                    )}
                  </button>
                  {addState === "error" && addError && (
                    <p className="text-xs text-red-600">{addError}</p>
                  )}
                </div>
              ) : project.document_ids.includes(currentDocumentId) ? (
                <p className="text-xs text-green-600">Current document is already in this project.</p>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* ── Project search ── */}
      {project && project.document_ids.length > 0 && (
        <div className="space-y-2">
          <SectionLabel>Search Project</SectionLabel>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKey}
              placeholder="Search across all project documents…"
              className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-rose-300"
            />
            <button
              onClick={handleSearch}
              disabled={!searchQuery.trim() || searchState === "loading"}
              className={[
                "px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
                !searchQuery.trim() || searchState === "loading"
                  ? "bg-gray-100 text-gray-400 cursor-default"
                  : "bg-rose-600 text-white hover:bg-rose-500",
              ].join(" ")}
            >
              {searchState === "loading" ? <Spinner className="w-4 h-4 border-rose-200" /> : "Search"}
            </button>
          </div>
          {searchState === "error" && searchError && (
            <p className="text-xs text-red-600">{searchError}</p>
          )}
          {searchState === "success" && searchResp && (
            <div className="space-y-2">
              <p className="text-xs text-gray-400">
                {searchResp.results.length === 0
                  ? `No results across ${searchResp.documents_searched} document(s).`
                  : `${searchResp.results.length} result${searchResp.results.length !== 1 ? "s" : ""} across ${searchResp.documents_searched} document(s) — ${searchResp.total_chunks_searched} chunks searched`}
              </p>
              <ProjectSearchResults results={searchResp.results} />
            </div>
          )}
        </div>
      )}

      {/* ── Project ask ── */}
      {project && project.document_ids.length > 0 && (
        <div className="space-y-2">
          <SectionLabel>Ask Project</SectionLabel>
          <div className="flex gap-2">
            <select
              value={askProvider}
              onChange={(e) => setAskProvider(e.target.value as ProjectProvider)}
              className="rounded-lg border border-gray-200 bg-white px-2 py-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-rose-300"
            >
              {PROJECT_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={askQuery}
              onChange={(e) => setAskQuery(e.target.value)}
              onKeyDown={handleAskKey}
              placeholder="Ask a question across all project documents…"
              className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-rose-300"
            />
            <button
              onClick={handleAsk}
              disabled={!askQuery.trim() || askState === "loading"}
              className={[
                "px-4 py-2 rounded-lg text-sm font-semibold transition-colors",
                !askQuery.trim() || askState === "loading"
                  ? "bg-gray-100 text-gray-400 cursor-default"
                  : "bg-rose-600 text-white hover:bg-rose-500",
              ].join(" ")}
            >
              {askState === "loading" ? <Spinner className="w-4 h-4 border-rose-200" /> : "Ask"}
            </button>
          </div>
          {askState === "error" && askError && (
            <p className="text-xs text-red-600">{askError}</p>
          )}
          {askState === "success" && askResp && (
            <div className="space-y-3">
              <div className="rounded-lg border border-gray-200 bg-white p-3">
                <p className="text-xs font-medium text-gray-400 mb-1.5">Answer</p>
                <pre className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed font-sans">
                  {askResp.answer}
                </pre>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "Provider",     value: askResp.provider },
                  { label: "Chunks used",  value: String(askResp.chunks_used) },
                  { label: "Docs sourced", value: String(askResp.document_count) },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg border border-rose-100 bg-white p-2 text-center">
                    <p className="text-sm font-bold text-gray-900">{value}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{label}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-400">
                Est. context: {askResp.estimated_context_tokens.toLocaleString()} tokens
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
