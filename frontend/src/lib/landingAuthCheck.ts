export const LANDING_AUTH_MESSAGE_TYPE = "stash:landing-auth-status";

const LOCAL_MARKETING_ORIGINS = new Set([
  "http://localhost:3100",
  "http://127.0.0.1:3100",
]);

export function allowedLandingParentOrigin(value: string | null): string | null {
  if (!value) return null;

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }

  if (LOCAL_MARKETING_ORIGINS.has(url.origin)) {
    return url.origin;
  }

  if (url.protocol !== "https:") {
    return null;
  }

  if (url.hostname === "joinstash.ai" || url.hostname === "www.joinstash.ai") {
    return url.origin;
  }

  return null;
}

export function landingAuthStatusMessage(signedIn: boolean) {
  return {
    type: LANDING_AUTH_MESSAGE_TYPE,
    signedIn,
  };
}
