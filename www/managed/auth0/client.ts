import { Auth0Client } from "@auth0/nextjs-auth0/server";

// Reads AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET / AUTH0_SECRET /
// APP_BASE_URL from env. Never imported when NEXT_PUBLIC_AUTH0_ENABLED !== "true".
//
// AUTH0_AUDIENCE is passed explicitly so the access token Auth0 issues is
// scoped to the Stash backend API (whose `/auth0/exchange` endpoint validates
// the audience claim). Without it, the SDK requests a token only valid at the
// userinfo endpoint — exchange would 401.
const audience = process.env.AUTH0_AUDIENCE;

export const auth0 = new Auth0Client(
  audience ? { authorizationParameters: { audience } } : undefined,
);
