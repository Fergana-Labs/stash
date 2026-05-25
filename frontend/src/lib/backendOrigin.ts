// Backend origin for SSR fetches.
//
// In docker/self-host setups, the frontend container needs to reach the
// backend over the internal docker network (e.g. http://backend:3456),
// not via the public URL the browser uses. Set BACKEND_INTERNAL_URL in
// the frontend container's env to point at the in-network hostname.
//
// Managed Auth0 deploys use the public API origin when no internal backend
// hostname is configured. Generic self-hosts still fall back to localhost.
export function resolveBackendOrigin(env: NodeJS.ProcessEnv = process.env): string {
  return (
    env.BACKEND_INTERNAL_URL ||
    env.NEXT_PUBLIC_API_URL ||
    (env.NEXT_PUBLIC_AUTH0_ENABLED === "true"
      ? "https://api.joinstash.ai"
      : "http://localhost:3456")
  );
}

export const SSR_BACKEND_ORIGIN = resolveBackendOrigin();
