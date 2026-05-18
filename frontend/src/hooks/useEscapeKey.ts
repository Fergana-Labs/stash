"use client";

import { useEffect, useRef } from "react";

interface EscapeHandler {
  id: symbol;
  onEscape: () => void;
}

const handlers: EscapeHandler[] = [];

function removeHandler(id: symbol) {
  const index = handlers.findIndex((handler) => handler.id === id);
  if (index >= 0) handlers.splice(index, 1);
}

function onDocumentKeyDown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;

  const handler = handlers[handlers.length - 1];
  if (!handler) return;

  event.preventDefault();
  handler.onEscape();
}

export function useEscapeKey(active: boolean, onEscape: () => void) {
  const onEscapeRef = useRef(onEscape);
  const idRef = useRef<symbol | null>(null);

  onEscapeRef.current = onEscape;
  if (!idRef.current) idRef.current = Symbol("escape-handler");

  useEffect(() => {
    if (!active) return;

    const id = idRef.current;
    if (!id) return;

    const wasEmpty = handlers.length === 0;
    handlers.push({
      id,
      onEscape: () => onEscapeRef.current(),
    });

    if (wasEmpty) document.addEventListener("keydown", onDocumentKeyDown);

    return () => {
      removeHandler(id);
      if (handlers.length === 0) {
        document.removeEventListener("keydown", onDocumentKeyDown);
      }
    };
  }, [active]);
}
