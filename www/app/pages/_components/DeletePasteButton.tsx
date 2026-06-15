"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { deletePaste } from "../actions";

// Delete control for the edit page header. Two-step (click → confirm) so a
// stray click can't destroy a page, then routes home on success.
export default function DeletePasteButton({ slug, token }: { slug: string; token: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setDeleting(true);
    setError("");
    const result = await deletePaste(slug, token);
    if (result.status === "error") {
      setDeleting(false);
      setError(result.message);
      return;
    }
    router.push("/pages");
  }

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="shrink-0 text-[12.5px] font-medium text-red-600 hover:text-red-700"
      >
        Delete
      </button>
    );
  }

  return (
    <span className="flex shrink-0 items-center gap-2 text-[12.5px]">
      {error ? (
        <span className="text-red-600">{error}</span>
      ) : (
        <span className="text-dim">Delete this page?</span>
      )}
      <button
        type="button"
        onClick={remove}
        disabled={deleting}
        className="font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
      >
        {deleting ? "Deleting…" : "Yes, delete"}
      </button>
      <button
        type="button"
        onClick={() => {
          setConfirming(false);
          setError("");
        }}
        className="text-dim hover:text-ink"
      >
        Cancel
      </button>
    </span>
  );
}
