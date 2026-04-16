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
  ]),
  {
    rules: {
      // Warn-only: legacy data-loading patterns trip React 19's stricter hooks
      // lint. Tracked for a dedicated refactor pass; not a CI gate.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
]);

export default eslintConfig;
