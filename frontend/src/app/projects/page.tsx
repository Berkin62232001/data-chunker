"use client";

import { useEffect, useState } from "react";
import { listProjects, type ProjectListItem } from "@/lib/api";

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

export default function ProjectsPage() {
  const [items, setItems] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then((data) => {
        setItems(data.projects);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load projects");
        setLoading(false);
      });
  }, []);

  return (
    <main className="max-w-3xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Group documents into projects for cross-document search and LLM queries.
        </p>
      </div>

      {loading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl border border-gray-200 bg-white p-4 animate-pulse h-16" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 px-6 py-16 text-center">
          <p className="text-sm font-medium text-gray-500">No projects yet</p>
          <p className="text-xs text-gray-400 mt-1 mb-4">
            Upload and chunk documents, then create a project from the document detail page.
          </p>
          <a
            href="/upload"
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-500 transition-colors"
          >
            Upload a document
          </a>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 mb-2">{items.length} project{items.length !== 1 ? "s" : ""}</p>
          {items.map((proj) => (
            <div
              key={proj.project_id}
              className="rounded-xl border border-gray-200 bg-white p-4 space-y-2"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-900">{proj.name}</p>
                  <p className="text-xs font-mono text-gray-400 truncate mt-0.5">{proj.project_id}</p>
                </div>
                <span className="shrink-0 px-2 py-0.5 rounded bg-indigo-100 text-indigo-700 text-xs font-semibold">
                  {proj.document_count} doc{proj.document_count !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="flex gap-4 text-xs text-gray-400">
                <span>Created {formatDate(proj.created_at)}</span>
                <span>Updated {formatDate(proj.updated_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-8 rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4">
        <p className="text-sm font-semibold text-indigo-800">How to create a project</p>
        <p className="text-xs text-indigo-600 mt-1">
          Open any fully-chunked document, scroll to the <strong>Project Analyzer</strong> section, and create a project there.
          You can then add more documents and search or ask questions across all of them.
        </p>
      </div>
    </main>
  );
}
