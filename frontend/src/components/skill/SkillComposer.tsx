"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

// Codex rejects skills outside these limits, so the form enforces them too.
const MAX_NAME_LENGTH = 64;
const MAX_DESCRIPTION_LENGTH = 1024;

/** Inline skill-creation form — a card that lives in the page, not a modal. */
export function SkillComposer({
  convertFolderName,
  onSubmit,
  onCancel,
}: {
  /** Folder being converted to a skill; when set the form only asks for the description. */
  convertFolderName?: string;
  onSubmit: (fields: { name: string; description: string }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const converting = convertFolderName !== undefined;
  const canSubmit =
    (converting || name.trim().length > 0) && description.trim().length > 0 && !submitting;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), description: description.trim() });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create skill");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
      }}
      className="rounded-xl border border-border bg-surface p-4"
    >
      <div className="text-[14px] font-medium text-foreground">
        {converting ? `Convert “${convertFolderName}” to a skill` : "New skill"}
      </div>
      <p className="mt-0.5 text-[12.5px] text-muted-foreground">
        A skill is a folder of instructions an agent loads when the task matches its description.
      </p>
      <div className="mt-3 space-y-3">
        {!converting && (
          <label className="block space-y-1.5">
            <span className="text-[12.5px] font-medium text-foreground">Name</span>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={MAX_NAME_LENGTH}
              placeholder="Release notes drafting"
            />
          </label>
        )}
        <label className="block space-y-1.5">
          <span className="text-[12.5px] font-medium text-foreground">
            When should an agent use it?
          </span>
          <Textarea
            autoFocus={converting}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={MAX_DESCRIPTION_LENGTH}
            rows={2}
            placeholder="Use when drafting release notes from merged PRs and changelog entries."
          />
        </label>
        <p className="text-[12px] text-muted-foreground">
          Agents read this to decide when to load the skill — name the tasks it covers.
        </p>
      </div>
      {error && <p className="mt-2 text-[12.5px] text-destructive">{error}</p>}
      <div className="mt-3 flex justify-end gap-1.5">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={!canSubmit}>
          {submitting ? "Creating…" : converting ? "Convert to skill" : "Create skill"}
        </Button>
      </div>
    </form>
  );
}
