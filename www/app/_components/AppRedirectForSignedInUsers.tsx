"use client";

import { useEffect } from "react";

const LANDING_AUTH_MESSAGE_TYPE = "stash:landing-auth-status";

type Props = {
  appUrl: string;
};

export default function AppRedirectForSignedInUsers({ appUrl }: Props) {
  useEffect(() => {
    const check = buildAuthCheck(appUrl, window.location.origin);
    if (!check) return;
    const { origin, url } = check;

    const iframe = document.createElement("iframe");
    iframe.src = url;
    iframe.hidden = true;
    iframe.tabIndex = -1;
    iframe.title = "";
    iframe.setAttribute("aria-hidden", "true");

    function onMessage(event: MessageEvent) {
      if (event.origin !== origin) return;
      if (!isSignedInMessage(event.data)) return;

      window.location.assign(appUrl);
    }

    window.addEventListener("message", onMessage);
    document.body.appendChild(iframe);

    return () => {
      window.removeEventListener("message", onMessage);
      iframe.remove();
    };
  }, [appUrl]);

  return null;
}

function buildAuthCheck(appUrl: string, parentOrigin: string) {
  let app: URL;
  try {
    app = new URL(appUrl);
  } catch {
    return null;
  }

  const checkUrl = new URL("/landing-auth-check", app.origin);
  checkUrl.searchParams.set("origin", parentOrigin);

  return {
    origin: app.origin,
    url: checkUrl.toString(),
  };
}

function isSignedInMessage(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;

  const message = data as { type?: unknown; signedIn?: unknown };
  return message.type === LANDING_AUTH_MESSAGE_TYPE && message.signedIn === true;
}
