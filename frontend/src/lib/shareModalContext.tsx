"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { ViewItemSpec } from "./api";

export interface ShareModalOpenOptions {
  stashId: string;
  stashName?: string;
  initial?: ViewItemSpec[];
  tab?: "new" | "manage";
}

interface ShareModalState extends ShareModalOpenOptions {
  open: boolean;
}

interface ShareModalContextValue {
  state: ShareModalState;
  open: (opts: ShareModalOpenOptions) => void;
  close: () => void;
  // Bumped whenever a share link is minted or revoked. Consumers (like the
  // stash home page) include it in deps to re-fetch their views list.
  version: number;
  bumpVersion: () => void;
}

const ShareModalContext = createContext<ShareModalContextValue | null>(null);

export function ShareModalProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ShareModalState>({
    open: false,
    stashId: "",
  });
  const [version, setVersion] = useState(0);

  const open = useCallback((opts: ShareModalOpenOptions) => {
    setState({
      open: true,
      stashId: opts.stashId,
      stashName: opts.stashName,
      initial: opts.initial,
      tab: opts.tab ?? "new",
    });
  }, []);

  const close = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
  }, []);

  const bumpVersion = useCallback(() => setVersion((v) => v + 1), []);

  const value = useMemo(
    () => ({ state, open, close, version, bumpVersion }),
    [state, open, close, version, bumpVersion]
  );
  return (
    <ShareModalContext.Provider value={value}>{children}</ShareModalContext.Provider>
  );
}

export function useShareModal(): ShareModalContextValue {
  const ctx = useContext(ShareModalContext);
  if (!ctx) {
    throw new Error("useShareModal must be used inside <ShareModalProvider>");
  }
  return ctx;
}
