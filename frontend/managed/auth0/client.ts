import { Auth0Client } from "@auth0/nextjs-auth0/server";

import { requireManagedAuth0Config } from "./config";
import {
  PostgresSessionStore,
  SESSION_ABSOLUTE_SECONDS,
  SESSION_INACTIVITY_SECONDS,
} from "./sessionStore";

// Reads AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET / AUTH0_SECRET /
// APP_BASE_URL / DATABASE_URL from env. Never imported when
// NEXT_PUBLIC_AUTH0_ENABLED !== "true".
//
// AUTH0_AUDIENCE is passed explicitly so the access token Auth0 issues is
// scoped to the Stash backend API. Without it, the SDK requests a token only
// valid at the userinfo endpoint, and backend session/CLI approval calls would
// fail JWT validation.
const { audience, auth0Secret, databaseUrl, databaseSsl } = requireManagedAuth0Config();

export const auth0 = new Auth0Client({
  authorizationParameters: { audience },
  // Server-side sessions: the cookie holds only an encrypted session ID; the
  // session itself lives in Postgres. Logout deletes the row, killing the
  // session across every tab and device at once — a rolling response racing
  // the logout can't resurrect it (sessionStore.update is a no-op for deleted
  // sessions). This is what makes rolling idle-timeout sessions (a SOC 2
  // control) safe to run.
  sessionStore: new PostgresSessionStore({ databaseUrl, databaseSsl, secret: auth0Secret }),
  session: {
    rolling: true,
    inactivityDuration: SESSION_INACTIVITY_SECONDS,
    absoluteDuration: SESSION_ABSOLUTE_SECONDS,
  },
});
