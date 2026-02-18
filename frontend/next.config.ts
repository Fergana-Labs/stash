import type { NextConfig } from "next";

const backend =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
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
