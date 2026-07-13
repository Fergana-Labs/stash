"use client";

import { useEffect, useState } from "react";
import type { Scope } from "./types";

// The scope every content request runs in: null = the user's personal stash,
// otherwise the workspace whose scope_user_id owns the shared knowledge base.
// api.ts stamps this onto requests synchronously, so the selection lives in a
// module cache backed by localStorage rather than in React state; a custom
// event keeps every mounted hook in sync within the tab (same shape as pins.ts).
export const SCOPE_HEADER = "X-Stash-Scope";
const SCOPE_KEY = "stash_scope";
const SCOPE_EVENT = "stash-scope-change";

// undefined = localStorage not read yet; null = personal scope.
let cache: Scope | null | undefined;

function read(): Scope | null {
  if (typeof window === "undefined") return null;
  if (cache !== undefined) return cache;
  const raw = localStorage.getItem(SCOPE_KEY);
  cache = raw ? (JSON.parse(raw) as Scope) : null;
  return cache;
}

export function getScope(): Scope | null {
  return read();
}

/** The X-Stash-Scope header value — null while in personal scope. */
export function getScopeUserId(): string | null {
  return read()?.scope_user_id ?? null;
}

export function setScope(scope: Scope | null): void {
  cache = scope;
  if (scope) localStorage.setItem(SCOPE_KEY, JSON.stringify(scope));
  else localStorage.removeItem(SCOPE_KEY);
  window.dispatchEvent(new Event(SCOPE_EVENT));
}

export function useScope(): Scope | null {
  // Seeded in an effect, not in useState, so the server render (always personal)
  // matches the client's first paint.
  const [scope, setScopeState] = useState<Scope | null>(null);

  useEffect(() => {
    const sync = () => setScopeState(read());
    sync();
    window.addEventListener(SCOPE_EVENT, sync);
    return () => window.removeEventListener(SCOPE_EVENT, sync);
  }, []);

  return scope;
}
