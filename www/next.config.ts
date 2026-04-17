import type { NextConfig } from "next";
import { fileURLToPath } from "node:url";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    root: path.dirname(fileURLToPath(import.meta.url)),
  },
  // `curl -fsSL https://stash.ac/install | bash` — same script as
  // /install.sh, served at the no-extension path most CLI installers use.
  async rewrites() {
    return [{ source: "/install", destination: "/install.sh" }];
  },
};

export default nextConfig;
