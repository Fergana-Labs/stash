// Pings IndexNow so Bing (and therefore ChatGPT search, which draws on the Bing
// index) picks up changes immediately instead of waiting for a recrawl. Google
// does not participate. Run after a deploy: node scripts/indexnow.mjs
const HOST = "www.joinstash.ai";
const KEY = "2f468d8597f71be279d20715525b59d7";

const sitemap = await fetch(`https://${HOST}/sitemap.xml`);
if (!sitemap.ok) throw new Error(`sitemap fetch failed: ${sitemap.status}`);

const urlList = [...(await sitemap.text()).matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
if (urlList.length === 0) throw new Error("sitemap contained no URLs");

const res = await fetch("https://api.indexnow.org/IndexNow", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({
    host: HOST,
    key: KEY,
    keyLocation: `https://${HOST}/${KEY}.txt`,
    urlList,
  }),
});
if (!res.ok) throw new Error(`IndexNow rejected the submission: ${res.status} ${await res.text()}`);
console.log(`IndexNow accepted ${urlList.length} URLs (${res.status})`);
