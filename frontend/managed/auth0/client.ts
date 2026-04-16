import { Auth0Client } from "@auth0/nextjs-auth0/server";

// Reads AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET / AUTH0_SECRET /
// APP_BASE_URL from env. Never imported when NEXT_PUBLIC_AUTH0_ENABLED !== "true".
export const auth0 = new Auth0Client();
