import type { NextRequest } from "next/server";

import { auth0 } from "./client";

export async function runAuth0Middleware(request: NextRequest) {
  return auth0.middleware(request);
}
