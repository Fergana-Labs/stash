"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiFetch, getToken, ApiError } from "../../../lib/api";

type Props = { slug: string; defaultName: string };

export default function ViewForkButton({ slug, defaultName }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "fork") return;
    if (!getToken()) return;
    void doFork();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function doFork() {
    setBusy(true);
    setError(null);
    try {
      const ws = await apiFetch<{ id: string }>(`/api/v1/views/${slug}/fork`, {
        method: "POST",
        body: JSON.stringify({ name: defaultName }),
      });
      router.push(`/workspaces/${ws.id}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Fork failed";
      setError(msg);
      setBusy(false);
    }
  }

  function onClick() {
    if (!getToken()) {
      const next = `/v/${slug}?action=fork`;
      router.push(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    void doFork();
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className="rounded-lg border border-brand bg-brand px-4 py-2 text-[14px] font-medium text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Forking…" : "Fork into a Stash"}
      </button>
      {error ? <p className="text-[12px] text-red-500">{error}</p> : null}
    </div>
  );
}
