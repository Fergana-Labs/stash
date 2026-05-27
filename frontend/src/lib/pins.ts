"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getWorkspacePins,
  getWorkspaceRecents,
  recordWorkspaceRecent,
  setWorkspacePins,
  type PinKind,
  type RecentEntry,
  type WorkspacePins,
} from "./api";

// Pins + recents live on the server, scoped per user. A small module cache
// keeps the sidebar dropdowns and the page views in sync within the tab: a
// toggle updates the cache and broadcasts an event so every hook re-reads.
const PINS_EVENT = "stash-pins-change";
const RECENTS_EVENT = "stash-recents-change";
const EMPTY_PINS: WorkspacePins = { stashes: [], sessions: [], files: [] };

const pinsCache = new Map<string, WorkspacePins>();
const pinsInflight = new Map<string, Promise<WorkspacePins>>();

function loadPins(workspaceId: string): Promise<WorkspacePins> {
  const cached = pinsCache.get(workspaceId);
  if (cached) return Promise.resolve(cached);
  const existing = pinsInflight.get(workspaceId);
  if (existing) return existing;
  const p = getWorkspacePins(workspaceId)
    .then((r) => {
      const value = { ...EMPTY_PINS, ...r };
      pinsCache.set(workspaceId, value);
      pinsInflight.delete(workspaceId);
      return value;
    })
    .catch((e) => {
      pinsInflight.delete(workspaceId);
      throw e;
    });
  pinsInflight.set(workspaceId, p);
  return p;
}

export function usePins(kind: PinKind, workspaceId: string) {
  const [ids, setIds] = useState<string[]>(
    () => pinsCache.get(workspaceId)?.[kind] ?? [],
  );

  useEffect(() => {
    if (!workspaceId) {
      setIds([]);
      return;
    }
    let cancelled = false;
    setIds(pinsCache.get(workspaceId)?.[kind] ?? []);
    loadPins(workspaceId)
      .then((r) => {
        if (!cancelled) setIds(r[kind]);
      })
      .catch(() => {});
    const onChange = () => setIds(pinsCache.get(workspaceId)?.[kind] ?? []);
    window.addEventListener(PINS_EVENT, onChange);
    return () => {
      cancelled = true;
      window.removeEventListener(PINS_EVENT, onChange);
    };
  }, [kind, workspaceId]);

  const toggle = useCallback(
    (id: string) => {
      if (!workspaceId) return;
      const current = pinsCache.get(workspaceId) ?? EMPTY_PINS;
      const list = current[kind] ?? [];
      const next = list.includes(id)
        ? list.filter((value) => value !== id)
        : [...list, id];
      pinsCache.set(workspaceId, { ...current, [kind]: next });
      setIds(next);
      window.dispatchEvent(new CustomEvent(PINS_EVENT));
      // Persist; on failure roll the cache back so the UI reflects reality.
      setWorkspacePins(workspaceId, kind, next).catch(() => {
        pinsCache.set(workspaceId, current);
        window.dispatchEvent(new CustomEvent(PINS_EVENT));
      });
    },
    [kind, workspaceId],
  );

  const pinnedSet = useMemo(() => new Set(ids), [ids]);
  const isPinned = (id: string) => pinnedSet.has(id);

  return { pinnedIds: ids, pinnedSet, isPinned, toggle };
}

const recentsCache = new Map<string, RecentEntry[]>();

// Recently-viewed object ids for the workspace, most-recent first. Refreshes
// when a view is recorded (see recordRecent).
export function useWorkspaceRecents(workspaceId: string): RecentEntry[] {
  const [recents, setRecents] = useState<RecentEntry[]>(
    () => recentsCache.get(workspaceId) ?? [],
  );

  useEffect(() => {
    if (!workspaceId) {
      setRecents([]);
      return;
    }
    let cancelled = false;
    setRecents(recentsCache.get(workspaceId) ?? []);
    const refresh = () =>
      getWorkspaceRecents(workspaceId)
        .then((r) => {
          recentsCache.set(workspaceId, r);
          if (!cancelled) setRecents(r);
        })
        .catch(() => {});
    refresh();
    window.addEventListener(RECENTS_EVENT, refresh);
    return () => {
      cancelled = true;
      window.removeEventListener(RECENTS_EVENT, refresh);
    };
  }, [workspaceId]);

  return recents;
}

// Stamp an object as just-viewed, then nudge any mounted recents lists to
// re-fetch. Fire-and-forget — a failed write shouldn't disrupt navigation.
export function recordRecent(workspaceId: string, objectId: string, kind: string) {
  if (!workspaceId || !objectId) return;
  // Defer through a resolved promise so even a synchronous failure in the
  // fetch layer can't bubble out of the caller's effect.
  Promise.resolve()
    .then(() => recordWorkspaceRecent(workspaceId, objectId, kind))
    .then(() => {
      recentsCache.delete(workspaceId);
      window.dispatchEvent(new CustomEvent(RECENTS_EVENT));
    })
    .catch(() => {});
}
