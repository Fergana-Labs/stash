import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:3456/api/:path*",
      },
      {
        source: "/skill/:path*",
        destination: "http://localhost:3456/skill/:path*",
      },
      {
        source: "/mcp/:path*",
        destination: "http://localhost:3456/mcp/:path*",
      },
      {
        source: "/health",
        destination: "http://localhost:3456/health",
      },
    ];
  },
};

export default nextConfig;
