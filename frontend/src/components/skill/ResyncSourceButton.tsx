"use client";

import { useEffect, useRef, useState } from "react";

import { syncSource } from "@/lib/api";

// Drive syncs on a minutes-long interval, so an edit made upstream stays
// invisible here until the next sync. This is the "I just edited my skill —
// confirm it's in Stash" affordance: trigger a sync, then poll the caller's
// refetch until the fresh copy shows up.
export default function ResyncSourceButton({
  sourceId,
  onRefresh,
}: {
  sourceId: string;
  onRefresh: () => Promise<void>;
}) {
  const [syncing, setSyncing] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function resync(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (syncing) return;
    setSyncing(true);
    try {
      await syncSource(sourceId);
      // The sync runs in a worker; poll until the caller's view reflects the
      // upstream edit. If the surface unmounts on refresh (e.g. a draft row
      // becoming runnable), the mounted ref ends the loop.
      for (let i = 0; i < 10 && mounted.current; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        await onRefresh();
      }
    } finally {
      if (mounted.current) setSyncing(false);
    }
  }

  return (
    <button
      type="button"
      onClick={(e) => void resync(e)}
      disabled={syncing}
      className={
        "whitespace-nowrap rounded-md border border-border px-2 py-1 text-[11.5px] font-medium " +
        (syncing
          ? "cursor-default text-muted-foreground"
          : "cursor-pointer text-foreground hover:bg-raised")
      }
    >
      {syncing ? "Syncing…" : "Re-sync"}
    </button>
  );
}
