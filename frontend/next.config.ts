import type { NextConfig } from "next";

const backend =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        // Only proxy versioned API calls to the backend.
        // /api/auth/* is reserved for the Auth0 SDK and must NOT be proxied.
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
      {
        source: "/skill/:path*",
        destination: `${backend}/skill/:path*`,
      },
      {
        source: "/health",
        destination: `${backend}/health`,
      },
    ];
  },
};

export default nextConfig;
