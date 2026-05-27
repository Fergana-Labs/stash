"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

// Pinned files/folders for the Files page quick-access strip. Pins are a flat
// set of object ids per workspace; the kind + route are resolved from the
// loaded items at render time, so folders, pages, tables, and files can all be
// pinned without separate buckets.
const PINS_KEY = "stash_files_pins";

type PinMap = Record<string, string[]>;

function readPinMap(): PinMap {
  if (typeof window === "undefined") return {};
  const raw = window.localStorage.getItem(PINS_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    window.localStorage.removeItem(PINS_KEY);
    return {};
  }
}

function writePinMap(map: PinMap) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PINS_KEY, JSON.stringify(map));
}

export function useFilePins(workspaceId: string) {
  const [ids, setIds] = useState<string[]>([]);

  useEffect(() => {
    setIds(readPinMap()[workspaceId] ?? []);
  }, [workspaceId]);

  const toggle = useCallback(
    (id: string) => {
      setIds((current) => {
        const next = current.includes(id)
          ? current.filter((value) => value !== id)
          : [...current, id];
        const map = readPinMap();
        map[workspaceId] = next;
        writePinMap(map);
        return next;
      });
    },
    [workspaceId],
  );

  const pinnedSet = useMemo(() => new Set(ids), [ids]);
  const isPinned = (id: string) => pinnedSet.has(id);

  return { pinnedIds: ids, pinnedSet, isPinned, toggle };
}
