import type { MetadataRoute } from "next";

const BASE = "https://joinstash.ai";

// Public marketing routes. Keep in sync with the nav/footer so new use-case
// pages get indexed as the site scales.
const ROUTES = [
  "",
  "/company-brain",
  "/memory",
  "/discover",
  "/docs",
  "/blog",
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
