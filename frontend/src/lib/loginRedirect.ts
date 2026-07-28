/** Where to send a viewer who has to sign in, and how to get them back.
 *
 * Viewers reach a page/file/folder link before we know whether they can read
 * it. When the read fails and they're signed out, they go to /login carrying
 * `next` — without it a successful sign-in drops them on the home page and the
 * link they clicked is lost.
 */

/** Same-origin absolute paths only: a `next` from the query string is
 * attacker-controlled, and "//evil.com" is a protocol-relative URL that would
 * bounce the user off-site after login. */
export function localNextPath(value: string | null): string {
  if (!value) return "";
  if (!value.startsWith("/") || value.startsWith("//")) return "";
  return value;
}

export function loginPathWithNext(path: string): string {
  return `/login?next=${encodeURIComponent(path)}`;
}
