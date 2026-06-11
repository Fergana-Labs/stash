"use server";

import { escapeHtml, sendPostmark } from "../_lib/postmark";

const LEADS_EMAIL = "sam@joinstash.ai";
const FROM_ADDRESS = "Stash <notifications@joinstash.ai>";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Tracking is best-effort: a down backend must never break a signup.
async function recordSignupEvent(variant: string, ref: string) {
  try {
    await fetch(`${API_URL}/api/v1/marketing/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "signup", variant, url: ref, referrer: "" }),
    });
  } catch (err) {
    console.error("marketing signup event failed", err);
  }
}

export type VariantSignupState = {
  status: "idle" | "ok" | "error";
  message?: string;
};

export async function submitVariantSignup(
  _prev: VariantSignupState,
  formData: FormData,
): Promise<VariantSignupState> {
  const email = String(formData.get("email") ?? "").trim();
  const roleCompany = String(formData.get("roleCompany") ?? "").trim();
  const referralSource = String(formData.get("referralSource") ?? "").trim();
  const agentUsage = String(formData.get("agentUsage") ?? "").trim();
  const useCases = formData.getAll("useCases").map(String);
  const otherUseCase = String(formData.get("otherUseCase") ?? "").trim();
  const variant = String(formData.get("variant") ?? "").trim();
  const ref = String(formData.get("ref") ?? "").trim();

  if (!email || !email.includes("@")) {
    return { status: "error", message: "Please enter a valid email address." };
  }

  const token = process.env.POSTMARK_SERVER_TOKEN;
  if (!token) {
    console.error("POSTMARK_SERVER_TOKEN is not set; cannot deliver signup submission", {
      email,
      variant,
    });
    return {
      status: "error",
      message: "Signups are not configured yet. Email sam@joinstash.ai directly.",
    };
  }

  const leadHtml = `
    <h2>Messaging test lead</h2>
    <p><strong>Variant:</strong> ${escapeHtml(variant) || "—"}</p>
    <p><strong>Email:</strong> ${escapeHtml(email)}</p>
    <p><strong>Role / company:</strong> ${escapeHtml(roleCompany) || "—"}</p>
    <p><strong>Found us via:</strong> ${escapeHtml(referralSource) || "—"}</p>
    <p><strong>Uses AI coding agents:</strong> ${escapeHtml(agentUsage) || "—"}</p>
    <p><strong>Use cases:</strong> ${useCases.map(escapeHtml).join(", ") || "—"}</p>
    <p><strong>Other use case:</strong></p>
    <p>${escapeHtml(otherUseCase).replace(/\n/g, "<br/>") || "—"}</p>
    <p><strong>Came from:</strong> ${escapeHtml(ref) || "—"}</p>
  `;

  const leadRes = await sendPostmark(token, {
    From: FROM_ADDRESS,
    To: LEADS_EMAIL,
    ReplyTo: email,
    Subject: `Messaging test lead — ${email} [${variant || "unknown"}]`,
    HtmlBody: leadHtml,
    MessageStream: "outbound",
  });

  if (!leadRes.ok) {
    console.error("Postmark signup lead send failed", leadRes.status, await leadRes.text());
    return {
      status: "error",
      message: "We couldn't save your signup. Please email sam@joinstash.ai.",
    };
  }

  await recordSignupEvent(variant, ref);
  return { status: "ok" };
}
