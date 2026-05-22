"use client";

import { useEffect, useState } from "react";

function configuredPublicApiBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL || "").trim().replace(/\/$/, "");
}

export function usePublicApiBase(): string {
  const [apiBase, setApiBase] = useState(configuredPublicApiBase);

  useEffect(() => {
    if (apiBase) return;
    setApiBase(window.location.origin);
  }, [apiBase]);

  return apiBase;
}
