import Link from "next/link";

import ScrollLink from "./ScrollLink";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";
// Signup must land on the auth flow — the app root is the public feed and
// shows a signed-out visitor no way to create an account.
const SIGNUP_URL = `${APP_URL}/login?mode=register`;
const CALL_URL = "/contact-sales";

// One consistent CTA pair everywhere across the landing: orange "Sign up free"
// as the primary goal, outlined "Book a call" as the enterprise secondary.
// Variant pages pass signupHref="#survey" so the primary scrolls to their form.
export default function CtaPair({
  signupHref = SIGNUP_URL,
  align = "start",
}: {
  signupHref?: string;
  align?: "start" | "center";
}) {
  const primaryClass =
    "inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover";
  return (
    <div
      className={`flex flex-wrap items-center gap-3 ${align === "center" ? "justify-center" : ""}`}
    >
      {signupHref.startsWith("#") ? (
        <ScrollLink to={signupHref} className={primaryClass}>
          Sign up free →
        </ScrollLink>
      ) : (
        <Link href={signupHref} className={primaryClass}>
          Sign up free →
        </Link>
      )}
      <Link
        href={CALL_URL}
        className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
      >
        Book a call
      </Link>
    </div>
  );
}
