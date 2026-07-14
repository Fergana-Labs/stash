export function requireAudience(env: NodeJS.ProcessEnv = process.env): string {
  const audience = env.AUTH0_AUDIENCE;
  if (!audience) {
    throw new Error("AUTH0_AUDIENCE must be set when managed Auth0 is enabled");
  }
  return audience;
}

export function requireHttpsAppBaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  const appBaseUrl = env.APP_BASE_URL;
  if (!appBaseUrl) {
    throw new Error("APP_BASE_URL must be set when managed Auth0 is enabled");
  }

  let url: URL;
  try {
    url = new URL(appBaseUrl);
  } catch {
    throw new Error("APP_BASE_URL must be an HTTPS origin without path, query, or fragment");
  }

  if (
    url.protocol !== "https:" ||
    !url.hostname ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("APP_BASE_URL must be an HTTPS origin without path, query, or fragment");
  }

  return appBaseUrl.replace(/\/$/, "");
}

export function requireAuth0Secret(env: NodeJS.ProcessEnv = process.env): string {
  const secret = env.AUTH0_SECRET;
  if (!secret) {
    throw new Error("AUTH0_SECRET must be set when managed Auth0 is enabled");
  }
  return secret;
}

// The server-side session store lives in the backend's Postgres.
export function requireDatabaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  const databaseUrl = env.DATABASE_URL;
  if (!databaseUrl) {
    throw new Error(
      "DATABASE_URL must be set when managed Auth0 is enabled (server-side session store)",
    );
  }
  return databaseUrl;
}

export function requireManagedAuth0Config(env: NodeJS.ProcessEnv = process.env): {
  audience: string;
  auth0Secret: string;
  databaseUrl: string;
  databaseSsl: boolean;
} {
  const audience = requireAudience(env);
  requireHttpsAppBaseUrl(env);
  return {
    audience,
    auth0Secret: requireAuth0Secret(env),
    databaseUrl: requireDatabaseUrl(env),
    databaseSsl: env.DATABASE_SSL === "true",
  };
}
