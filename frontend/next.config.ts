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
    ];
  },
};

export default nextConfig;
