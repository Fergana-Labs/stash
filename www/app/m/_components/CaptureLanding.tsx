"use client";

import { useEffect } from "react";

export const LANDING_URL_KEY = "stash-landing-url";

// Records the full landing URL (including the ad's utm params) so the signup
// form can attach it to the lead email — document.referrer can't do this:
// Next's client-side navigation to /signup doesn't update it. Also fires a
// first-party view beacon so views per variant are counted in our own data.
export default function CaptureLanding({ variant }: { variant: string }) {
  useEffect(() => {
    sessionStorage.setItem(LANDING_URL_KEY, window.location.href);
    navigator.sendBeacon(
      "/api/track",
      JSON.stringify({
        kind: "view",
        variant,
        url: window.location.href,
        referrer: document.referrer,
      }),
    );
  }, [variant]);
  return null;
}
