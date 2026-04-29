"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { forkWorkspace, getToken } from "../../../lib/api";

type Props = { workspaceId: string; defaultName: string };

export default function ForkButton({ workspaceId, defaultName }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // After signing in, we land back on /s/<id>?action=fork. Run the fork once
  // we have a token, then redirect into the fresh workspace.
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
      const ws = await forkWorkspace(workspaceId, defaultName);
      router.push(`/workspaces/${ws.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fork failed");
      setBusy(false);
    }
  }

  function onClick() {
    if (!getToken()) {
      const next = `/s/${workspaceId}?action=fork`;
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
        {busy ? "Forking…" : "Fork this Stash"}
      </button>
      {error ? <p className="text-[12px] text-red-500">{error}</p> : null}
    </div>
  );
}
