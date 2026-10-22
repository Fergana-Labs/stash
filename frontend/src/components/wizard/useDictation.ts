"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* The Web Speech API is not in TypeScript's DOM lib; this is the slice we use. */
interface Recognition {
  continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start(): void; stop(): void;
}
type RecognitionCtor = new () => Recognition;

function ctor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Browser dictation: speech becomes text in the composer as you talk. `base`
 * is what was typed before listening started; interim words show live and are
 * replaced by the final transcript.
 */
export function useDictation(onText: (text: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const rec = useRef<Recognition | null>(null);
  const base = useRef("");
  const finals = useRef("");
  useEffect(() => setSupported(ctor() !== null), []);

  const stop = useCallback(() => { rec.current?.stop(); }, []);
  const start = useCallback((current: string) => {
    const Ctor = ctor();
    if (!Ctor) return;
    const r = new Ctor();
    r.continuous = true; r.interimResults = true; r.lang = navigator.language || "en-US";
    base.current = current ? `${current.trimEnd()} ` : "";
    finals.current = "";
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) finals.current += res[0].transcript; else interim += res[0].transcript;
      }
      onText(base.current + finals.current + interim);
    };
    r.onerror = (e) => { setError(e.error === "not-allowed" ? "Microphone access was blocked." : e.error === "no-speech" ? "" : `Voice input stopped (${e.error}).`); };
    r.onend = () => { setListening(false); rec.current = null; };
    rec.current = r; setError(""); setListening(true);
    r.start();
  }, [onText]);
  useEffect(() => () => rec.current?.stop(), []);
  return { supported, listening, error, start, stop };
}
