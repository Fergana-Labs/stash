// Backend origin for SSR fetches.
//
// In docker/self-host setups, the frontend container needs to reach the
// backend over the internal docker network (e.g. http://backend:3456),
// not via the public URL the browser uses. Set BACKEND_INTERNAL_URL in
// the frontend container's env to point at the in-network hostname.
//
// Falls back to localhost:3456 for vanilla `npm run dev`.
export const SSR_BACKEND_ORIGIN =
  process.env.BACKEND_INTERNAL_URL ||
  "http://localhost:3456";
