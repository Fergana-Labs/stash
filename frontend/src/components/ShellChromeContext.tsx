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
}

interface Ctx extends ShellChrome {
  setShareAction: (node: ReactNode | null) => void;
}

const ShellChromeContext = createContext<Ctx>({
  shareAction: null,
  setShareAction: () => {},
});

export function ShellChromeProvider({ children }: { children: ReactNode }) {
  const [shareAction, setShareAction] = useState<ReactNode | null>(null);
  return (
    <ShellChromeContext.Provider value={{ shareAction, setShareAction }}>
      {children}
    </ShellChromeContext.Provider>
  );
}

export function useShellChromeValue(): ShellChrome {
  const { shareAction } = useContext(ShellChromeContext);
  return { shareAction };
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
