// Render the website-taste demo fixtures (first screen, 1440x900) with JS and network disabled.
// Usage (from frontend/): node ../scripts/render_taste_comparison.cjs
const { chromium } = require("../frontend/node_modules/@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const dir = path.join(__dirname, "../frontend/public/demo/website-taste");
const arms = ["base", "skill", "gepa", "posttrained"];

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const arm of arms) {
      const page = await browser.newPage({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
        javaScriptEnabled: false,
      });
      await page.route("**/*", (route) => route.abort());
      const html = fs.readFileSync(path.join(dir, `${arm}.html`), "utf8");
      await page.setContent(html, { waitUntil: "load" });
      const out = path.join(dir, `${arm}.png`);
      await page.screenshot({ path: out, type: "png", animations: "disabled" });
      console.log(arm, fs.statSync(out).size);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
