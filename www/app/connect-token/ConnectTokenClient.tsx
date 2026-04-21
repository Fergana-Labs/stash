"use client";

import { useState } from "react";

type Props = {
  apiUrl: string;
  sessionId: string;
  device?: string;
  userName: string;
};

// Client-side "Authorize CLI" confirmation. Explicit click triggers the Auth0
// → backend token exchange + CLI approve. Without this gate, the CLI would
// silently receive a token any time a user with an active Auth0 session loaded
// this URL.
export default function ConnectTokenClient({ apiUrl, sessionId, device, userName }: Props) {
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "done" }
    | { kind: "error"; message: string; detail?: string }
  >({ kind: "idle" });

  async function authorize() {
    setState({ kind: "submitting" });
    try {
      const tokenRes = await fetch("/auth/access-token");
      if (!tokenRes.ok) throw new Error("Auth0 session expired — reload this page.");
      const { token } = await tokenRes.json();

      const exchangeUrl = new URL(`${apiUrl}/api/v1/auth0/exchange`);
      if (device) exchangeUrl.searchParams.set("device", device);
      const exchangeRes = await fetch(exchangeUrl.toString(), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!exchangeRes.ok) {
        const detail = await exchangeRes.text().catch(() => "");
        throw Object.assign(new Error("The Stash backend rejected your Auth0 token."), {
          detail: detail.slice(0, 500),
        });
      }
      const data = (await exchangeRes.json()) as { api_key: string };

      const approveRes = await fetch(
        `${apiUrl}/api/v1/users/cli-auth/sessions/${encodeURIComponent(sessionId)}/approve`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${data.api_key}` },
        },
      );
      if (!approveRes.ok) {
        const detail = await approveRes.text().catch(() => "");
        throw Object.assign(
          new Error("Could not hand the token to your CLI — your CLI session may have expired."),
          { detail: detail.slice(0, 500) },
        );
      }

      setState({ kind: "done" });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sign-in failed";
      const detail = (err as { detail?: string })?.detail;
      setState({ kind: "error", message, detail });
    }
  }

  if (state.kind === "done") {
    return (
      <div className="mt-6">
        <p className="inline-flex items-center gap-2 rounded-full bg-raised px-3 py-1.5 text-[13px] font-mono text-ink">
          <span className="h-1.5 w-1.5 rounded-full bg-brand" />
          CLI authorized as {userName}
        </p>
        <p className="mt-4 max-w-[560px] text-[16px] leading-[1.6] text-dim">
          Head back to your terminal — <code>stash signin</code> has the token and will finish
          wiring up your workspace. You can close this tab.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-3">
      <button
        type="button"
        onClick={authorize}
        disabled={state.kind === "submitting"}
        className="rounded-xl bg-brand px-5 py-2.5 text-[14px] font-semibold text-white transition-all hover:bg-brand-hover disabled:opacity-60"
      >
        {state.kind === "submitting" ? "Authorizing..." : "Authorize CLI"}
      </button>
      {state.kind === "error" && (
        <div className="max-w-[560px]">
          <p className="text-[14px] text-red-400">{state.message}</p>
          {state.detail ? (
            <pre className="mt-2 overflow-x-auto rounded-lg bg-raised px-4 py-3 font-mono text-[12px] leading-[1.5] text-ink">
              {state.detail}
            </pre>
          ) : null}
        </div>
      )}
    </div>
  );
}
