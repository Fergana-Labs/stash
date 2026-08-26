import type { MetadataRoute } from "next";

const BASE = "https://www.joinstash.ai";

// Public marketing routes. Keep in sync with the nav/footer so new pages get
// indexed as the site scales.
const ROUTES = [
  "",
  "/internal-agents",
  "/external-agents",
  "/pricing",
  "/security",
  "/docs",
  "/docs/quickstart",
  "/docs/concepts",
  "/docs/cli",
  "/docs/self-hosting",
  "/docs/contributing",
  "/blog",
  "/blog/how-to-build-a-company-brain",
  "/blog/three-dimensions-agent-memory-store",
  "/blog/open-questions-in-memory",
  "/blog/why-no-great-consumer-ai",
  "/blog/context-gold-rush",
  "/blog/containerizing-memory",
  "/contact-sales",
  "/privacy",
  "/terms",
];

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((path) => ({
    url: `${BASE}${path}`,
    changeFrequency: path === "" ? "weekly" : "monthly",
    priority: path === "" ? 1 : 0.7,
  }));
}
