"use client";

import { useRef, useState, type DragEvent } from "react";
import { uploadTranscript } from "../lib/api";

type Status = "idle" | "uploading" | "done" | "error";

interface SessionUploadProps {
  onUploaded?: () => void;
}

function isJsonl(file: File): boolean {
  return file.name.toLowerCase().endsWith(".jsonl");
}

function defaultSessionId(file: File): string {
  return file.name.replace(/\.jsonl$/i, "").trim();
}

export default function SessionUpload({ onUploaded }: SessionUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");

  async function handleFile(file: File) {
    if (!isJsonl(file)) {
      setStatus("error");
      setMessage("Sessions only accept .jsonl transcripts.");
      return;
    }

    const sessionId = defaultSessionId(file);
    if (!sessionId) {
      setStatus("error");
      setMessage("Transcript filename must include a session id.");
      return;
    }

    setStatus("uploading");
    setMessage(`Uploading ${file.name}...`);
    try {
      const result = await uploadTranscript(file, sessionId, "manual-upload");
      setStatus("done");
      setMessage(
        result.skipped
          ? `${sessionId} already exists.`
          : `${sessionId} added with ${result.imported} event${result.imported === 1 ? "" : "s"}.`
      );
      onUploaded?.();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Upload failed");
    }
  }

  function isFilesDrag(event: DragEvent): boolean {
    return Array.from(event.dataTransfer.types).includes("Files");
  }

  function handleDragOver(event: DragEvent) {
    if (!isFilesDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragActive(true);
  }

  function handleDrop(event: DragEvent) {
    if (!isFilesDrag(event)) return;
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  const tone =
    status === "error"
      ? "text-red-600"
      : status === "done"
        ? "text-[var(--color-brand-700)]"
        : "text-muted-foreground";

  return (
    <div
      onDragEnter={() => setDragActive(true)}
      onDragLeave={() => setDragActive(false)}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className={
        "rounded-lg border border-dashed px-3 py-2 transition-colors " +
        (dragActive
          ? "border-[var(--color-brand-400)] bg-[var(--color-brand-50)]"
          : "border-border bg-surface/40")
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={status === "uploading"}
          className="cursor-pointer rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-50"
        >
          {status === "uploading" ? "Uploading..." : "+ Add session"}
        </button>
        <span className="text-[12px] text-muted-foreground">Drop a .jsonl transcript</span>
        <input
          ref={inputRef}
          type="file"
          accept=".jsonl"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) handleFile(file);
            if (inputRef.current) inputRef.current.value = "";
          }}
        />
      </div>
      {message && <div className={"mt-1 text-[11.5px] " + tone}>{message}</div>}
    </div>
  );
}
