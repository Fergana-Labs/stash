"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { SkillItemSpec } from "./api";

export interface ShareModalOpenOptions {
  workspaceId: string;
  workspaceName?: string;
  initial?: SkillItemSpec[];
}

interface ShareModalState extends ShareModalOpenOptions {
  open: boolean;
}

interface ShareModalContextValue {
  state: ShareModalState;
  open: (opts: ShareModalOpenOptions) => void;
  close: () => void;
  // Bumped whenever a Skill URL is minted or revoked. Consumers include it
  // in deps to re-fetch their Skills list.
  version: number;
  bumpVersion: () => void;
}

const ShareModalContext = createContext<ShareModalContextValue | null>(null);

export function ShareModalProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ShareModalState>({
    open: false,
    workspaceId: "",
  });
  const [version, setVersion] = useState(0);

  const open = useCallback((opts: ShareModalOpenOptions) => {
    setState({
      open: true,
      workspaceId: opts.workspaceId,
      workspaceName: opts.workspaceName,
      initial: opts.initial,
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
