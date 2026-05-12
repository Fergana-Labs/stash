"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { createWorkspaceHistoryEvent, uploadFile } from "../lib/api";
import type { User } from "../lib/types";

interface StashQuickAddProps {
  stashId: string;
  user: User;
  onAdded?: () => void;
}

type Status = "idle" | "saving" | "saved" | "error";

export default function StashQuickAdd({ stashId, user, onAdded }: StashQuickAddProps) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [dragActive, setDragActive] = useState(false);
  const [hint, setHint] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Track nested dragenter/leave so we don't flicker when crossing children
  const dragDepth = useRef(0);

  function flashHint(text: string, ms = 1500) {
    setHint(text);
    window.setTimeout(() => setHint(""), ms);
  }

  async function handleTextSubmit(e: FormEvent) {
    e.preventDefault();
    const text = value.trim();
    if (!text || status === "saving") return;

    setStatus("saving");
    const title = text.split("\n")[0].slice(0, 80) || "Manual source";
    try {
      await createWorkspaceHistoryEvent(stashId, {
        agent_name: user.name || "user",
        event_type: "source",
        content: text === title ? text : `${title}\n\n${text}`,
        session_id: `manual-source-${Date.now()}`,
        metadata: {
          source: "manual_ui",
          title,
          added_by: user.display_name || user.name,
        },
      });
    } catch {
      setStatus("error");
      flashHint("Couldn’t save — try again", 2500);
      window.setTimeout(() => setStatus("idle"), 2500);
      return;
    }
    setValue("");
    setStatus("saved");
    flashHint("Added to stash");
    onAdded?.();
    window.setTimeout(() => setStatus("idle"), 1500);
  }

  async function handleFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (!list.length || status === "saving") return;
    setStatus("saving");
    flashHint(list.length === 1 ? `Uploading ${list[0].name}…` : `Uploading ${list.length} files…`, 8000);
    try {
      for (const f of list) {
        await uploadFile(stashId, f);
      }
    } catch {
      setStatus("error");
      flashHint("Upload failed — try again", 2500);
      window.setTimeout(() => setStatus("idle"), 2500);
      return;
    }
    setStatus("saved");
    flashHint(list.length === 1 ? `${list[0].name} added` : `${list.length} files added`);
    onAdded?.();
    window.setTimeout(() => setStatus("idle"), 1500);
  }

  function isFilesDrag(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  function handleDragEnter(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    setDragActive(true);
  }

  function handleDragLeave(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragActive(false);
  }

  function handleDragOver(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
  }

  function handleDrop(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDragActive(false);
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
  }

  const statusText =
    hint ||
    (status === "saved" ? "Added to stash" : "");
  const statusTone =
    status === "error"
      ? "text-red-500"
      : status === "saved"
      ? "text-[var(--color-brand-700)]"
      : "text-muted";

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className={
        "group relative rounded-xl border-2 border-dashed px-4 py-3.5 transition-colors " +
        (dragActive
          ? "border-[var(--color-brand-500)] bg-[var(--color-brand-50)]"
          : "border-border bg-surface/40 hover:border-[var(--color-brand-300)] hover:bg-surface/60")
      }
    >
      <form onSubmit={handleTextSubmit} className="flex items-center gap-2.5">
        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-[var(--color-brand-500)] text-[14px] font-semibold leading-none text-white">
          +
        </span>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={
            dragActive
              ? "Drop to upload to this stash…"
              : "Paste a link, type a note, or drop a file here"
          }
          disabled={status === "saving"}
          className="h-7 flex-1 bg-transparent text-[13.5px] text-foreground outline-none placeholder:text-muted disabled:opacity-60"
        />
        {value.trim() ? (
          <button
            type="submit"
            disabled={status === "saving"}
            className="rounded-md bg-[var(--color-brand-600)] px-3 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
          >
            {status === "saving" ? "Adding…" : "Add"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={status === "saving"}
            className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-muted hover:bg-raised hover:text-foreground disabled:opacity-60"
            title="Choose a file to upload"
          >
            Upload file
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) handleFiles(e.target.files);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
        />
      </form>
      <div className="mt-1.5 pl-[34px] text-[11.5px] leading-tight">
        {statusText ? (
          <span className={"font-medium " + statusTone}>{statusText}</span>
        ) : (
          <span className="text-muted">
            Drop a file anywhere in this box, or press Enter to save a link or note
          </span>
        )}
      </div>
    </div>
  );
}
