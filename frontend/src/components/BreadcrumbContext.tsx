"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export type Crumb = {
  label: string;
  href?: string;
  onClick?: () => void;
};

interface Ctx {
  crumbs: Crumb[] | null;
  setCrumbs: (c: Crumb[] | null) => void;
}

const BreadcrumbContext = createContext<Ctx>({
  crumbs: null,
  setCrumbs: () => {},
});

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[] | null>(null);
  return (
    <BreadcrumbContext.Provider value={{ crumbs, setCrumbs }}>
      {children}
    </BreadcrumbContext.Provider>
  );
}

export function useBreadcrumbsValue() {
  return useContext(BreadcrumbContext).crumbs;
}

/**
 * Register breadcrumbs for the current page. Pages pass the crumbs (the
 * workspace name is prepended automatically by the TopBar) and a dependency
 * key that changes when the crumbs should be re-registered.
 */
export function useBreadcrumbs(crumbs: Crumb[], depKey: string) {
  const { setCrumbs } = useContext(BreadcrumbContext);
  const stable = useCallback(() => setCrumbs(crumbs), [setCrumbs, crumbs]);
  useEffect(() => {
    stable();
    return () => setCrumbs(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depKey]);
}
