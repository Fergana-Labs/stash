"use client";

import { useEffect, useRef } from "react";

/** Page navigation yields Escape to text editors and dismissible UI. */
export function useEscapeBack(onBack: () => void) {
  const callback = useRef(onBack);
  useEffect(() => { callback.current = onBack; }, [onBack]);
  useEffect(() => {
    let mounted = true;
    function keydown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.repeat) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="combobox"]')) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], [data-slot="popover-content"][data-state="open"]')) return;
      // Let existing Escape handlers claim the event before navigating.
      queueMicrotask(() => { if (mounted && !event.defaultPrevented) callback.current(); });
    }
    document.addEventListener("keydown", keydown);
    return () => { mounted = false; document.removeEventListener("keydown", keydown); };
  }, []);
}
