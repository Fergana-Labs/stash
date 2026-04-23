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

export function useBreadcrumbs(crumbs: Crumb[], depKey: string) {
  const { setCrumbs } = useContext(BreadcrumbContext);
  const crumbsRef = useRef(crumbs);

  useEffect(() => {
    crumbsRef.current = crumbs;
  }, [crumbs]);

  useEffect(() => {
    setCrumbs(crumbsRef.current);
    return () => setCrumbs(null);
  }, [depKey, setCrumbs]);
}
