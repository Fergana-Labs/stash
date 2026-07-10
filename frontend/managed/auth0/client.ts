import { Auth0Client } from "@auth0/nextjs-auth0/server";

import { requireManagedAuth0Config } from "./config";

// Reads AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET / AUTH0_SECRET /
// APP_BASE_URL from env. Never imported when NEXT_PUBLIC_AUTH0_ENABLED !== "true".
//
// AUTH0_AUDIENCE is passed explicitly so the access token Auth0 issues is
// scoped to the Stash backend API. Without it, the SDK requests a token only
// valid at the userinfo endpoint, and backend session/CLI approval calls would
// fail JWT validation.
const { audience } = requireManagedAuth0Config();

export const auth0 = new Auth0Client({
  authorizationParameters: { audience },
  // Rolling sessions re-write the session cookie on every response, so a
  // request in flight while /auth/logout deletes the cookie can resurrect it
  // and undo the sign-out. Fixed-duration sessions only write the cookie at
  // login and token refresh.
  session: {
    rolling: false,
    absoluteDuration: 60 * 60 * 24 * 30, // 30 days, then re-login
  },
});
