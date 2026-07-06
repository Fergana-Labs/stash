"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

const GLOBAL_SCOPE = "__global__";

interface ShellChrome {
  shareAction: ReactNode | null;
}

interface Ctx {
  shareActions: Record<string, ReactNode | null>;
  setShareAction: (scopeId: string, node: ReactNode | null) => void;
}

const ShellChromeContext = createContext<Ctx>({
  shareActions: {},
  setShareAction: () => {},
});
const ShellChromeScopeContext = createContext(GLOBAL_SCOPE);

export function ShellChromeProvider({ children }: { children: ReactNode }) {
  const [shareActions, setShareActions] = useState<Record<string, ReactNode | null>>({});
  const setShareAction = useCallback((scopeId: string, node: ReactNode | null) => {
    setShareActions((current) => {
      if (node === null) {
        const next = { ...current };
        delete next[scopeId];
        return next;
      }
      return { ...current, [scopeId]: node };
    });
  }, []);

  return (
    <ShellChromeContext.Provider value={{ shareActions, setShareAction }}>
      {children}
    </ShellChromeContext.Provider>
  );
}

export function ShellChromeScope({
  scopeId,
  children,
}: {
  scopeId: string;
  children: ReactNode;
}) {
  return (
    <ShellChromeScopeContext.Provider value={scopeId}>
      {children}
    </ShellChromeScopeContext.Provider>
  );
}

export function useShellChromeValue(scopeId = GLOBAL_SCOPE): ShellChrome {
  const { shareActions } = useContext(ShellChromeContext);
  return { shareAction: shareActions[scopeId] ?? null };
}

// Page-side hook: registers a share action with the surrounding AppShell and
// clears it on unmount so stale buttons don't leak across navigations.
export function useShareAction(node: ReactNode | null) {
  const scopeId = useContext(ShellChromeScopeContext);
  const { setShareAction } = useContext(ShellChromeContext);
  useEffect(() => {
    setShareAction(scopeId, node);
    return () => setShareAction(scopeId, null);
  }, [node, scopeId, setShareAction]);
}
