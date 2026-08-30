// Dead-CSS contract for the landing page (STAS-146, STAS-147).
//
// www/app/globals.css once styled the /pages markdown pastebin: a Tiptap
// editor surface whose routes were deleted in ef6027d7 (#1065) while its
// styling text survived. Two halves are pinned here — editor styling must not
// outlive an editor, and the `.prose` typography the blog actually renders
// must survive the deletion.
//
// STAS-147 added the second tranche: styling for spans and carets a script used
// to inject at runtime, plus a legal-page class hook that was never defined.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const WWW = fileURLToPath(new URL("../", import.meta.url));
const CSS = readFileSync(join(WWW, "app/globals.css"), "utf8");

const DEAD_EDITOR_SELECTORS = [
  ".tiptap",
  ".is-editor-empty",
  ".file-page-body",
  ".ProseMirror",
];

// Nothing in www can ever put these names on an element: the collaboration
// server was deleted in #982, the comment-anchor span is injected only by the
// product app (which styles it in its own stylesheet), and no www code animates
// anything. Bare names rather than selectors so the keyframes are covered too.
const DEAD_RUNTIME_TOKENS = [
  "collaboration-cursor",
  "data-comment-id",
  "rise-in",
  "live-pulse",
  "cursor-blink",
];

function sourcesUnder(dir) {
  const found = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...sourcesUnder(path));
    else if (/\.(ts|tsx)$/.test(entry.name)) found.push(path);
  }
  return found;
}

const wwwSources = [
  ...sourcesUnder(join(WWW, "app")),
  ...sourcesUnder(join(WWW, "lib")),
  ...sourcesUnder(join(WWW, "managed")),
];

test("editor styling never outlives an editor", () => {
  const editorImported = wwwSources.some((file) =>
    /@tiptap|prosemirror/i.test(readFileSync(file, "utf8")),
  );
  if (editorImported) return; // a real www editor may bring its styling back

  for (const selector of DEAD_EDITOR_SELECTORS) {
    assert.ok(
      !CSS.includes(selector),
      `globals.css still styles ${selector} with nothing in www rendering it`,
    );
  }
});

test("the prose typography the blog renders survives", () => {
  const posts = sourcesUnder(join(WWW, "app/blog")).filter((file) =>
    file.endsWith("page.tsx"),
  );
  assert.ok(posts.length > 1, "blog posts are the prose consumers");

  for (const post of posts) {
    const text = readFileSync(post, "utf8");
    assert.ok(
      !DEAD_EDITOR_SELECTORS.some((selector) => text.includes(selector.slice(1))),
      `${post} references removed editor classes`,
    );
  }
  assert.ok(
    posts.some((post) => readFileSync(post, "utf8").includes('className="prose ')),
    "no blog post renders the prose class anymore",
  );

  assert.match(CSS, /^\.prose \{$/m, "the .prose palette block was deleted");
  assert.match(CSS, /--tw-prose-body: var\(--text\);/);
  assert.match(CSS, /\.prose :where\(blockquote\)/);
  assert.match(CSS, /@plugin "@tailwindcss\/typography";/);
});

test("server-fetched content cannot arrive as raw HTML", () => {
  // The dead classes could only reappear in served markup if www injected
  // backend HTML into the DOM. It renders fetched JSON through React instead.
  const injectsRawHtml = wwwSources.some((file) =>
    /rehype-raw|rehypeRaw/.test(readFileSync(file, "utf8")),
  );
  assert.equal(injectsRawHtml, false);
});

test("runtime-only styling never outlives the runtime that injected it", () => {
  for (const token of DEAD_RUNTIME_TOKENS) {
    assert.ok(
      !CSS.includes(token),
      `globals.css still ships ${token} styling for a surface www cannot render`,
    );
  }
});

test("legal pages carry no style hook that no stylesheet defines", () => {
  // Defining the class is a legitimate answer to the hook; silently ignoring it
  // is not. Only a stylesheet that never defines it makes the markup dishonest.
  if (CSS.includes(".legal-prose")) return;

  for (const file of wwwSources) {
    assert.ok(
      !readFileSync(file, "utf8").includes("legal-prose"),
      `${file} applies legal-prose, which no stylesheet defines`,
    );
  }
});
