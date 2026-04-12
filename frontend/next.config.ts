import type { NextConfig } from "next";

const backend =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      // Browser HTTP traffic goes through the BFF proxy at /api/proxy/*.
      // The /api/v1/* rewrite is kept only for non-browser clients (CLI, agents)
      // that call the Next.js server directly and expect the legacy path.
      // WebSocket upgrades bypass the route-handler system and must still be
      // proxied at the network level (Caddy/nginx in production).
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
      {
        source: "/skill/:path*",
        destination: `${backend}/skill/:path*`,
      },
      {
        source: "/mcp",
        destination: `${backend}/mcp`,
      },
      {
        source: "/mcp/:path*",
        destination: `${backend}/mcp/:path*`,
      },
      {
        source: "/health",
        destination: `${backend}/health`,
      },
    ];
  },
};

export default nextConfig;
