import type { NextConfig } from "next";
import { fileURLToPath } from "node:url";
import path from "node:path";

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
        source: "/:path*",
        has: [{ type: "host", value: "www.joinstash.ai" }],
        destination: "https://joinstash.ai/:path*",
        permanent: true,
      },
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
};

export default nextConfig;
