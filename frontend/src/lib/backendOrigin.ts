const BACKEND_ORIGIN_ERROR =
  "Set BACKEND_INTERNAL_URL or NEXT_PUBLIC_API_URL for frontend server-side backend requests.";

export function resolveBackendOrigin(env: NodeJS.ProcessEnv = process.env): string {
  const origin = env.BACKEND_INTERNAL_URL || env.NEXT_PUBLIC_API_URL;
  if (!origin) throw new Error(BACKEND_ORIGIN_ERROR);
  return origin;
}

export const SSR_BACKEND_ORIGIN = resolveBackendOrigin();
