import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Static assets served as-is — designer reference, runtime globals.
    "public/**",
  ]),
  {
    rules: {
      // The app intentionally fetches route data from effects.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
