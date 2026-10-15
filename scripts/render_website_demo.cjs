// Render an untrusted, self-contained HTML artifact without network or scripts.
const { chromium } = require("../frontend/node_modules/@playwright/test");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 960 },
      deviceScaleFactor: 1,
      javaScriptEnabled: false,
    });
    await page.route("**/*", (route) => route.abort());
    const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:">`;
    const html = fs.readFileSync(process.argv[2], "utf8");
    await page.setContent(
      html.replace(/<head[^>]*>/i, (match) => match + policy),
      { waitUntil: "load" },
    );
    await page.screenshot({
      path: process.argv[3],
      type: "png",
      animations: "disabled",
    });
    console.log(
      JSON.stringify({
        width: 1440,
        height: 960,
        bytes: fs.statSync(process.argv[3]).size,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
