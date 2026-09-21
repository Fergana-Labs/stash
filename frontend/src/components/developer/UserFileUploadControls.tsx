"use client";

import { useRef, useState } from "react";

import { uploadFile } from "@/lib/api";

// Hand this user a file from the console. The server stamps the file row's
// end_user_id, so only this user's agent (and the developer) can read it.
export default function UserFileUploadControls({
  externalUserId,
  onAdded,
}: {
  externalUserId: string;
  onAdded: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setBusy(true);
    setError("");
    try {
      await uploadFile(file, null, externalUserId);
      onAdded();
    } catch (cause) {
      if (!(cause instanceof Error)) throw cause;
      setError(cause.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="mt-3">
      <input
        ref={inputRef}
        type="file"
        hidden
        data-testid="user-file-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60"
      >
        {busy ? "Uploading..." : "Upload a file"}
      </button>
      {error && <div className="mt-2 text-[12.5px] text-error">{error}</div>}
    </div>
  );
}
