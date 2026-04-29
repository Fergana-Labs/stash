"use client";

import { useActionState } from "react";

import { adminLogin, type LoginState } from "./actions";

const initial: LoginState = { status: "idle" };

export default function AdminLoginPage() {
  const [state, formAction, pending] = useActionState(adminLogin, initial);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen max-w-[420px] flex-col justify-center px-7 py-16">
        <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          Admin
        </p>
        <h1 className="mt-3 font-display text-[32px] font-black leading-[1.05] tracking-[-0.03em] text-ink">
          Sign in
        </h1>
        <p className="mt-3 text-[14px] leading-[1.55] text-dim">
          Restricted area. Enter the admin password to continue.
        </p>

        <form action={formAction} className="mt-8 space-y-4">
          <div>
            <label
              htmlFor="password"
              className="mb-2 block font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              autoFocus
              required
              className="w-full rounded-md border border-border-subtle bg-background px-3 py-2.5 text-[14px] text-ink outline-none transition focus:border-brand"
            />
          </div>
          {state.status === "error" && (
            <p className="text-[13px] text-red-500">{state.message}</p>
          )}
          <button
            type="submit"
            disabled={pending}
            className="w-full rounded-md bg-ink px-4 py-2.5 text-[14px] font-medium text-background transition hover:opacity-90 disabled:opacity-60"
          >
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
