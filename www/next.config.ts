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
