"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useRef,
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
 * Register breadcrumbs for the current page. `depKey` drives when the
 * context gets updated — change it whenever the crumb content changes.
 *
 * A ref holds the latest `crumbs` so the effect always reads the freshest
 * array at fire time, avoiding the stale-closure hole that a direct
 * [crumbs]-dep would introduce (new array every render = infinite loop).
 */
export function useBreadcrumbs(crumbs: Crumb[], depKey: string) {
  const { setCrumbs } = useContext(BreadcrumbContext);
  const crumbsRef = useRef(crumbs);
  crumbsRef.current = crumbs;

  useEffect(() => {
    setCrumbs(crumbsRef.current);
    return () => setCrumbs(null);
  }, [depKey, setCrumbs]);
}
