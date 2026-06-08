export const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
];

// Anti-clickjacking. Applied to every route except published Stash embeds,
// which must stay iframe-able from anywhere (stashEmbedHeaders below).
export const frameGuardHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
];

export const stashEmbedHeaders = [
  { key: "Content-Security-Policy", value: "frame-ancestors *" },
];
