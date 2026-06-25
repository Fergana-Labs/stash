import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import Logo from "../../../_components/Logo";
import SignupForm from "../../_components/SignupForm";
import { VARIANTS } from "../../variants";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export function generateStaticParams() {
  return Object.keys(VARIANTS).map((variant) => ({ variant }));
}

export const metadata: Metadata = {
  title: "Sign up · Stash",
  robots: { index: false },
};

export default async function SignupPage({
  params,
}: {
  params: Promise<{ variant: string }>;
}) {
  const { variant } = await params;
  if (!VARIANTS[variant]) notFound();
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex h-16 max-w-[1080px] items-center px-7">
          <Link
            href={`/m/${variant}`}
            className="flex items-center gap-2.5 font-display text-[20px] font-bold tracking-[-0.03em] text-ink"
          >
            <Logo size={28} />
            stash
          </Link>
        </div>
      </header>
      <div className="mx-auto max-w-[640px] px-7 py-16 md:py-20">
        <h1 className="text-center font-display text-[clamp(28px,3.4vw,42px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Sign up for Stash.
        </h1>
        <p className="mx-auto mt-4 max-w-[460px] text-center text-[16px] leading-[1.6] text-dim">
          Tell us a bit about you and we&apos;ll get your account set up.
        </p>
        <SignupForm variant={variant} appUrl={APP_URL} />
      </div>
    </main>
  );
}
