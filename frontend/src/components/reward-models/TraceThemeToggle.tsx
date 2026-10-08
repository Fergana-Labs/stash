"use client";

import { useEffect, useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";

function subscribe(change: () => void) {
  const observer = new MutationObserver(change);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

export default function TraceThemeToggle() {
  const dark = useSyncExternalStore(subscribe, () => document.documentElement.dataset.theme === "dark", () => false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function apply() {
      let saved: string | null = null;
      try { saved = localStorage.getItem("stash-theme"); } catch { /* Theme still works without storage. */ }
      document.documentElement.dataset.theme = saved === "dark" || saved !== "light" && media.matches ? "dark" : "light";
      document.documentElement.style.colorScheme = document.documentElement.dataset.theme;
    }
    apply();
    media.addEventListener("change", apply);
    window.addEventListener("storage", apply);
    return () => { media.removeEventListener("change", apply); window.removeEventListener("storage", apply); };
  }, []);
  const label = `Switch to ${dark ? "light" : "dark"} mode`;
  return <button type="button" aria-label={label} title={label} onClick={() => {
    const theme = dark ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try { localStorage.setItem("stash-theme", theme); } catch { /* Optional persistence. */ }
  }} className="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-surface hover:text-foreground">{dark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}</button>;
}
