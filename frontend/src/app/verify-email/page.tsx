"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

// Landing page for the emailed verification link. Unauthenticated on purpose:
// the click can come from any browser, and the token alone is the proof.
function VerifyEmailInner() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"working" | "verified" | "failed">("working");

  useEffect(() => {
    if (!token) {
      setState("failed");
      return;
    }
    fetch("/api/v1/users/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }).then(
      (res) => setState(res.ok ? "verified" : "failed"),
      () => setState("failed"),
    );
  }, [token]);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[680px] px-6 pb-24 pt-20">
        {state === "working" && <h1 className="text-2xl font-bold">Verifying your email…</h1>}
        {state === "verified" && (
          <>
            <h1 className="text-2xl font-bold">Email verified</h1>
            <p className="mt-4 text-[16px] leading-[1.6]">
              You&apos;re all set. If your company has a Stash workspace on this email&apos;s
              domain, you&apos;re now a member of it.
            </p>
            <Link href="/" className="mt-6 inline-block underline">
              Go to your Stash
            </Link>
          </>
        )}
        {state === "failed" && (
          <>
            <h1 className="text-2xl font-bold">This link didn&apos;t work</h1>
            <p className="mt-4 text-[16px] leading-[1.6]">
              It may have expired or been replaced by a newer email. Request a fresh link
              from your account and use the most recent one.
            </p>
          </>
        )}
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailInner />
    </Suspense>
  );
}
