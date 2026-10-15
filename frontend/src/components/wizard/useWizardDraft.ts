"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { wzSaveDraft } from "@/lib/wizard-api";
import { errorMessage } from "@/components/reward-models/rm-text";

const key = (id: string) => `stash-wizard-draft:${id}`;

/** Server persistence plus a local fallback for closing a tab before its save completes. */
export function useWizardDraft(sessionId: string) {
  const [input, setValue] = useState("");
  const [status, setStatus] = useState("Saved");
  const [error, setError] = useState("");
  const latest = useRef("");
  const saved = useRef("");
  const ready = useRef(false);
  const mounted = useRef(true);
  const writing = useRef<Promise<boolean> | null>(null);

  const setInput = useCallback((text: string) => {
    latest.current = text; setValue(text); setStatus("Saving…"); setError("");
    try { localStorage.setItem(key(sessionId), text); } catch { /* Server save still works. */ }
  }, [sessionId]);

  const recover = useCallback((text: string) => {
    // A failed submission must not erase either that message or newer typing.
    setInput([text, latest.current].filter(Boolean).join("\n\n"));
  }, [setInput]);

  const load = useCallback((remote: string) => {
    let text = remote;
    try { text = localStorage.getItem(key(sessionId)) ?? remote; } catch { /* Use the server copy. */ }
    saved.current = remote; latest.current = text; ready.current = true; setValue(text);
    setStatus(text === remote ? "Saved" : "Saving…");
  }, [sessionId]);

  const flush = useCallback((): Promise<boolean> => {
    if (writing.current) return writing.current;
    if (!ready.current || latest.current === saved.current) return Promise.resolve(true);
    const run = async () => {
      while (latest.current !== saved.current) {
        const text = latest.current;
        try { await wzSaveDraft(sessionId, text); saved.current = text; }
        catch (e) {
          if (mounted.current) { setError(errorMessage(e)); setStatus("Saved on this device"); }
          return false;
        }
      }
      if (mounted.current) { setStatus("Saved"); setError(""); }
      // Keep a dirty local fallback only; another device's server draft can now be restored.
      try { localStorage.removeItem(key(sessionId)); } catch { /* Optional local fallback. */ }
      return true;
    };
    writing.current = run().finally(() => { writing.current = null; });
    return writing.current;
  }, [sessionId]);

  useEffect(() => {
    mounted.current = true;
    const saveOnLeave = () => { void flush(); };
    window.addEventListener("pagehide", saveOnLeave);
    return () => { mounted.current = false; window.removeEventListener("pagehide", saveOnLeave); void flush(); };
  }, [flush]);
  useEffect(() => {
    const timer = setTimeout(() => { void flush(); }, 500);
    return () => clearTimeout(timer);
  }, [input, flush]);
  return { input, setInput, recover, load, flush, status, error };
}
