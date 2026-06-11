export const securityHeaders = [
  // Logged-in app pages must not be frameable by other origins (clickjacking);
  // the embed route below overrides this for published Skill embeds.
  { key: "Content-Security-Policy", value: "frame-ancestors 'self'" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
];

export const skillEmbedHeaders = [
  { key: "Content-Security-Policy", value: "frame-ancestors *" },
];
