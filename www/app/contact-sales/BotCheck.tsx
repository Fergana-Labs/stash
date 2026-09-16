"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type Turnstile = {
  render: (container: HTMLElement, options: {
    sitekey: string;
    action: string;
    callback: (token: string) => void;
    "expired-callback": () => void;
    "error-callback": () => void;
  }) => string;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile: Turnstile;
  }
}

export default function BotCheck({ attempt, onToken }: {
  attempt: number;
  onToken: (token: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;

  useEffect(() => {
    if (!ready || !siteKey || !container.current) return;
    const id = window.turnstile.render(container.current, {
      sitekey: siteKey,
      action: "contact_sales",
      callback: (token) => {
        setFailed(false);
        onToken(token);
      },
      "expired-callback": () => onToken(""),
      "error-callback": () => {
        setFailed(true);
        onToken("");
      },
    });
    return () => window.turnstile.remove(id);
  }, [ready, siteKey, attempt, onToken]);

  if (!siteKey) {
    return <p role="alert">Demo requests are unavailable: verification is not configured.</p>;
  }

  return (
    <div>
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        onReady={() => setReady(true)}
        onError={() => {
          setFailed(true);
          onToken("");
        }}
      />
      <div ref={container} />
      {failed && <p role="alert">Verification failed to load. Please reload this page to try again.</p>}
    </div>
  );
}
