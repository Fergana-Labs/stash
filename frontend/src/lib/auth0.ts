import { Auth0Client } from "@auth0/nextjs-auth0/server";

export function getAuth0Client() {
  // Support both AUTH0_DOMAIN and AUTH0_ISSUER_BASE_URL (stash_web compat)
  const issuerBaseUrl = process.env.AUTH0_ISSUER_BASE_URL;
  const domain =
    process.env.AUTH0_DOMAIN ??
    (issuerBaseUrl ? new URL(issuerBaseUrl).hostname : undefined);

  // Support multiple base URL env var names
  const appBaseUrl =
    process.env.APP_BASE_URL ??
    process.env.AUTH0_BASE_URL ??
    process.env.NEXT_PUBLIC_APP_BASE_URL ??
    (process.env.NODE_ENV !== "production" ? "http://localhost:3457" : undefined);

  if (!domain || !appBaseUrl) {
    throw new Error(
      "Auth0 is not fully configured. Set AUTH0_DOMAIN (or AUTH0_ISSUER_BASE_URL) " +
        "and APP_BASE_URL (or AUTH0_BASE_URL).",
    );
  }

  return new Auth0Client({
    domain,
    appBaseUrl,
    authorizationParameters: {
      audience: process.env.AUTH0_API_AUDIENCE ?? process.env.AUTH0_AUDIENCE,
      scope: "openid profile email offline_access",
    },
    signInReturnToPath: "/",
    routes: {
      login: "/api/auth/login",
      logout: "/api/auth/logout",
      callback: "/api/auth/callback",
      backChannelLogout: "/api/auth/backchannel-logout",
    },
  });
}
