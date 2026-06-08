import type { NextConfig } from "next";

import {
  frameGuardHeaders,
  securityHeaders,
  stashEmbedHeaders,
} from "./src/lib/securityHeaders";

// Rewrites are evaluated by the Next.js node server (server-side). Set
// BACKEND_INTERNAL_URL for same-network backends (Docker/self-host) or
// NEXT_PUBLIC_API_URL for managed deployments with a separate API host.
const backend = process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL;

if (!backend) {
  throw new Error(
    "Set BACKEND_INTERNAL_URL or NEXT_PUBLIC_API_URL for frontend backend rewrites.",
  );
}

const acceptsJson = ".*application/json.*";
const acceptsMarkdown = ".*(text/markdown|text/plain).*";
const acceptsHtml = ".*text/html.*";
const agentUserAgent = "^(?!.*[Mm]ozilla).+";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return {
      // These run before App Router pages so `.md` and `.json` are content
      // formats, not slug suffixes.
      beforeFiles: [
        {
          source: "/stashes/:slug.md",
          destination: `${backend}/api/v1/stashes/:slug?format=text`,
        },
        {
          source: "/stashes/:slug.json",
          destination: `${backend}/api/v1/stashes/:slug`,
        },
        {
          source: "/stashes/:slug/items/:type/:id.md",
          destination: `${backend}/api/v1/stashes/:slug/items/:type/:id?format=text`,
        },
        {
          source: "/stashes/:slug/items/:type/:id.json",
          destination: `${backend}/api/v1/stashes/:slug/items/:type/:id`,
        },
        {
          source: "/stashes/:slug",
          has: [{ type: "header", key: "accept", value: acceptsJson }],
          destination: `${backend}/api/v1/stashes/:slug`,
        },
        {
          source: "/stashes/:slug/items/:type/:id",
          has: [{ type: "header", key: "accept", value: acceptsJson }],
          destination: `${backend}/api/v1/stashes/:slug/items/:type/:id`,
        },
        {
          source: "/stashes/:slug",
          has: [{ type: "header", key: "accept", value: acceptsMarkdown }],
          destination: `${backend}/api/v1/stashes/:slug?format=text`,
        },
        {
          source: "/stashes/:slug/items/:type/:id",
          has: [{ type: "header", key: "accept", value: acceptsMarkdown }],
          destination: `${backend}/api/v1/stashes/:slug/items/:type/:id?format=text`,
        },
        {
          source: "/stashes/:slug",
          has: [{ type: "header", key: "user-agent", value: agentUserAgent }],
          missing: [{ type: "header", key: "accept", value: acceptsHtml }],
          destination: `${backend}/api/v1/stashes/:slug?format=text`,
        },
        {
          source: "/stashes/:slug/items/:type/:id",
          has: [{ type: "header", key: "user-agent", value: agentUserAgent }],
          missing: [{ type: "header", key: "accept", value: acceptsHtml }],
          destination: `${backend}/api/v1/stashes/:slug/items/:type/:id?format=text`,
        },
        {
          source: "/stashes/:slug",
          missing: [
            { type: "header", key: "user-agent" },
            { type: "header", key: "accept", value: acceptsHtml },
          ],
          destination: `${backend}/api/v1/stashes/:slug?format=text`,
        },
        {
          source: "/stashes/:slug/items/:type/:id",
          missing: [
            { type: "header", key: "user-agent" },
            { type: "header", key: "accept", value: acceptsHtml },
          ],
          destination: `${backend}/api/v1/stashes/:slug/items/:type/:id?format=text`,
        },
        {
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
        {
          source: "/llms.txt",
          destination: `${backend}/llms.txt`,
        },
      ],
    };
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
      {
        // Anti-clickjacking on every route except published embeds, which the
        // more specific rule below re-opens with frame-ancestors *.
        source: "/((?!stashes/[^/]+/embed).*)",
        headers: frameGuardHeaders,
      },
      {
        // Published Stash embeds must be iframe-able from anywhere.
        source: "/stashes/:slug/embed",
        headers: stashEmbedHeaders,
      },
    ];
  },
};

export default nextConfig;
