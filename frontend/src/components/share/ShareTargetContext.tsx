"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import type { ShareableObjectType } from "../../lib/api";

export interface ShareTarget {
  objectType: ShareableObjectType;
  objectId: string;
  label: string;
}

interface Ctx {
  target: ShareTarget | null;
  setTarget: (t: ShareTarget | null) => void;
}

const ShareTargetContext = createContext<Ctx>({
  target: null,
  setTarget: () => {},
});

export function ShareTargetProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<ShareTarget | null>(null);
  return (
    <ShareTargetContext.Provider value={{ target, setTarget }}>
      {children}
    </ShareTargetContext.Provider>
  );
}

export function useShareTargetValue() {
  return useContext(ShareTargetContext).target;
}

export function useSetShareTarget(target: ShareTarget | null, depKey: string) {
  const { setTarget } = useContext(ShareTargetContext);
  const ref = useRef(target);

  useEffect(() => {
    ref.current = target;
  }, [target]);

  useEffect(() => {
    setTarget(ref.current);
    return () => setTarget(null);
  }, [depKey, setTarget]);
}
