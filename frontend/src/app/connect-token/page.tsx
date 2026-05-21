"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function ConnectTokenPage() {
  return (
    <Suspense fallback={<RedirectShell />}>
      <ConnectTokenRedirect />
    </Suspense>
  );
}

function ConnectTokenRedirect() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const session = searchParams.get("session");
    if (!session) {
      router.replace("/login");
      return;
    }

    const params = new URLSearchParams({ cli: session });
    router.replace(`/login?${params.toString()}`);
  }, [router, searchParams]);

  return <RedirectShell />;
}

function RedirectShell() {
  return <div className="min-h-screen bg-base" />;
}
