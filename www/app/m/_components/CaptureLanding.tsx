"use client";

import { useEffect } from "react";

export const LANDING_URL_KEY = "stash-landing-url";

// Records the full landing URL (including the ad's utm params) so the signup
// form can attach it to the lead email. document.referrer can't do this:
// Next's client-side navigation to /signup doesn't update it.
export default function CaptureLanding() {
  useEffect(() => {
    sessionStorage.setItem(LANDING_URL_KEY, window.location.href);
  }, []);
  return null;
}
