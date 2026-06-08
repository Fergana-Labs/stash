import type { NextConfig } from "next";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { securityHeaders } from "./lib/security-headers";

const MANAGED_APP_URL =
  process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    root: path.dirname(fileURLToPath(import.meta.url)),
  },
  async redirects() {
    return [
      {
        source: "/install",
        destination:
          "https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh",
        permanent: false,
      },
      {
        source: "/join/:code",
        destination: `${MANAGED_APP_URL}/join/:code`,
        permanent: false,
      },
      {
        source: "/login",
        destination: `${MANAGED_APP_URL}/login`,
        permanent: false,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
