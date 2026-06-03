"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";

interface ShellChrome {
  shareAction: ReactNode | null;
  activeWorkspaceId: string | null;
}

interface Ctx extends ShellChrome {
  setShareAction: (node: ReactNode | null) => void;
  setActiveWorkspaceId: (id: string | null) => void;
}

const ShellChromeContext = createContext<Ctx>({
  shareAction: null,
  activeWorkspaceId: null,
  setShareAction: () => {},
  setActiveWorkspaceId: () => {},
});

export function ShellChromeProvider({ children }: { children: ReactNode }) {
  const [shareAction, setShareAction] = useState<ReactNode | null>(null);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(
    null,
  );
  return (
    <ShellChromeContext.Provider
      value={{
        shareAction,
        activeWorkspaceId,
        setShareAction,
        setActiveWorkspaceId,
      }}
    >
      {children}
    </ShellChromeContext.Provider>
  );
}

export function useShellChromeValue(): ShellChrome {
  const { shareAction, activeWorkspaceId } = useContext(ShellChromeContext);
  return { shareAction, activeWorkspaceId };
}

// Page-side hook: registers a share action with the surrounding AppShell and
// clears it on unmount so stale buttons don't leak across navigations.
export function useShareAction(node: ReactNode | null) {
  const { setShareAction } = useContext(ShellChromeContext);
  useEffect(() => {
    setShareAction(node);
    return () => setShareAction(null);
  }, [node, setShareAction]);
}

// Page-side hook: tells AppShell which workspace the current page belongs to
// when the URL alone doesn't carry it (e.g. /cartridges/[slug] resolves its
// workspace from the loaded stash).
export function useActiveWorkspaceId(id: string | null) {
  const { setActiveWorkspaceId } = useContext(ShellChromeContext);
  useEffect(() => {
    if (id == null) return;
    setActiveWorkspaceId(id);
  }, [id, setActiveWorkspaceId]);
}
