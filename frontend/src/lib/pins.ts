"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getPins,
  getMyRecents,
  recordRecent as recordMyRecent,
  setPins,
  type PinKind,
  type Pins,
  type RecentEntry,
} from "./api";

// Pins + recents live on the server, scoped to the current user. A small module
// cache keeps the sidebar dropdowns and the page views in sync within the tab: a
// toggle updates the cache and broadcasts an event so every hook re-reads.
const PINS_EVENT = "skill-pins-change";
const RECENTS_EVENT = "skill-recents-change";
const EMPTY_PINS: Pins = { skills: [], sessions: [], files: [] };

let pinsCache: Pins | null = null;
let pinsInflight: Promise<Pins> | null = null;

function loadPins(): Promise<Pins> {
  if (pinsCache) return Promise.resolve(pinsCache);
  if (pinsInflight) return pinsInflight;
  pinsInflight = getPins()
    .then((r) => {
      const value = { ...EMPTY_PINS, ...r };
      pinsCache = value;
      pinsInflight = null;
      return value;
    })
    .catch((e) => {
      pinsInflight = null;
      throw e;
    });
  return pinsInflight;
}

export function usePins(kind: PinKind) {
  const [ids, setIds] = useState<string[]>(() => pinsCache?.[kind] ?? []);

  useEffect(() => {
    let cancelled = false;
    setIds(pinsCache?.[kind] ?? []);
    loadPins()
      .then((r) => {
        if (!cancelled) setIds(r[kind]);
      })
      .catch(() => {});
    const onChange = () => setIds(pinsCache?.[kind] ?? []);
    window.addEventListener(PINS_EVENT, onChange);
    return () => {
      cancelled = true;
      window.removeEventListener(PINS_EVENT, onChange);
    };
  }, [kind]);

  const toggle = useCallback(
    (id: string) => {
      const current = pinsCache ?? EMPTY_PINS;
      const list = current[kind] ?? [];
      const next = list.includes(id)
        ? list.filter((value) => value !== id)
        : [...list, id];
      pinsCache = { ...current, [kind]: next };
      setIds(next);
      window.dispatchEvent(new CustomEvent(PINS_EVENT));
      // Persist; on failure roll the cache back so the UI reflects reality.
      setPins(kind, next).catch(() => {
        pinsCache = current;
        window.dispatchEvent(new CustomEvent(PINS_EVENT));
      });
    },
    [kind],
  );

  const pinnedSet = useMemo(() => new Set(ids), [ids]);
  const isPinned = (id: string) => pinnedSet.has(id);

  return { pinnedIds: ids, pinnedSet, isPinned, toggle };
}

let recentsCache: RecentEntry[] | null = null;

// Recently-viewed object ids for the user, most-recent first. Refreshes when a
// view is recorded (see recordRecent).
export function useRecents(): RecentEntry[] {
  const [recents, setRecents] = useState<RecentEntry[]>(
    () => recentsCache ?? [],
  );

  useEffect(() => {
    let cancelled = false;
    setRecents(recentsCache ?? []);
    const refresh = () =>
      getMyRecents()
        .then((r) => {
          recentsCache = r;
          if (!cancelled) setRecents(r);
        })
        .catch(() => {});
    refresh();
    window.addEventListener(RECENTS_EVENT, refresh);
    return () => {
      cancelled = true;
      window.removeEventListener(RECENTS_EVENT, refresh);
    };
  }, []);

  return recents;
}

// Stamp an object as just-viewed, then nudge any mounted recents lists to
// re-fetch. Fire-and-forget — a failed write shouldn't disrupt navigation.
export function recordRecent(objectId: string, kind: string) {
  if (!objectId) return;
  // Defer through a resolved promise so even a synchronous failure in the
  // fetch layer can't bubble out of the caller's effect.
  Promise.resolve()
    .then(() => recordMyRecent(objectId, kind))
    .then(() => {
      recentsCache = null;
      window.dispatchEvent(new CustomEvent(RECENTS_EVENT));
    })
    .catch(() => {});
}
