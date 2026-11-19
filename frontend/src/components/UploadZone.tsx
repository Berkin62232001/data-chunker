"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { uploadFile } from "@/lib/api";

export function UploadZone() {
  const router = useRouter();
  const [isDragging, setIsDragging] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback(
    async (file: File) => {
      setState("loading");
      setError(null);
      try {
        const result = await uploadFile(file);
        router.push(`/documents/${result.document_id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
        setState("error");
      }
    },
    [router],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) processFile(file);
    },
    [processFile],
  );

  const handleClick = useCallback(() => inputRef.current?.click(), []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) processFile(file);
      e.target.value = "";
    },
    [processFile],
  );

  const isUploading = state === "loading";

  return (
    <div className="space-y-3">
      <div
        onClick={handleClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={[
          "flex flex-col items-center justify-center w-full rounded-[var(--radius)] cursor-pointer",
          "border-2 border-dashed transition-all duration-200 select-none py-12 px-6 text-center",
          isUploading
            ? "opacity-60 pointer-events-none"
            : isDragging
              ? "border-[var(--a-500)] bg-[var(--a-soft)]"
              : "border-[var(--border-2)] bg-[var(--surface)] hover:border-[var(--a-500)] hover:bg-[var(--surface-2)]",
        ].join(" ")}
        style={isDragging ? { boxShadow: "0 0 0 4px var(--ring)" } : undefined}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.html,.png,.jpg,.jpeg,.webp"
          onChange={handleInputChange}
        />

        <div
          className="dz-icon w-[68px] h-[68px] rounded-[20px] flex items-center justify-center mb-5"
        >
          {isUploading ? (
            <svg
              width={30}
              height={30}
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth={1.8}
              strokeLinecap="round"
              className="animate-spin"
            >
              <path d="M20 11a8 8 0 00-14-4.5L4 8"/><path d="M4 4v4h4"/>
            </svg>
          ) : (
            <svg
              width={30}
              height={30}
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth={1.8}
              strokeLinecap="round"
            >
              <path d="M12 16V4m0 0l-4 4m4-4l4 4"/><path d="M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2"/>
            </svg>
          )}
        </div>

        <p className="text-[1.05rem] font-[640] mb-1.5" style={{ color: "var(--text)" }}>
          {isUploading ? "Uploading & profiling…" : isDragging ? "Release to upload" : "Drag & drop a file here"}
        </p>
        <p className="text-sm" style={{ color: "var(--text-2)" }}>
          or{" "}
          <span className="font-medium" style={{ color: "var(--a-soft-fg)" }}>
            browse your computer
          </span>{" "}
          · up to 100 MB
        </p>
        <div
          className="flex items-center gap-1.5 mt-4 text-xs"
          style={{ color: "var(--text-3)" }}
        >
          <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
            <rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>
          </svg>
          Files never leave this machine
        </div>
      </div>

      {state === "error" && error && (
        <div
          className="rounded-[var(--radius-xs)] border px-4 py-3 text-sm"
          style={{ background: "#fde8e6", borderColor: "#f7cbc6", color: "#c2382b" }}
        >
          <span className="font-semibold">Upload failed:</span> {error}
        </div>
      )}
    </div>
  );
}
