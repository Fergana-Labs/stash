"use server";

import { escapeHtml, sendPostmark } from "../_lib/postmark";

const SALES_EMAIL = "sam@joinstash.ai";
const FROM_ADDRESS = "Stash <notifications@joinstash.ai>";

export type SnapshotLeadState = {
  status: "idle" | "ok" | "error";
  message?: string;
};

// Receives the completed assessment interview: contact info, the full chat
// transcript, and the model-produced qualification. Delivers the lead to
// sales; the visitor gets their report rendered client-side.
export async function submitSnapshotLead(payload: {
  name: string;
  email: string;
  business: string;
  score: number;
  tier: string;
  transcript: [string, string][];
}): Promise<SnapshotLeadState> {
  const { name, email, business, score, tier, transcript } = payload;

  if (!name.trim() || !email.includes("@")) {
    return { status: "error", message: "Name and a valid email are required." };
  }

  const token = process.env.POSTMARK_SERVER_TOKEN;
  if (!token) {
    console.error("POSTMARK_SERVER_TOKEN is not set; cannot deliver snapshot lead", {
      name,
      email,
      business,
    });
    return {
      status: "error",
      message: "We couldn't save your snapshot. Email sam@joinstash.ai directly.",
    };
  }

  const transcriptRows = transcript
    .map(
      ([speaker, text]) =>
        `<tr><td style="padding:4px 12px 4px 0;color:#6B655B;vertical-align:top">${escapeHtml(speaker)}</td><td style="padding:4px 0">${escapeHtml(text)}</td></tr>`,
    )
    .join("");

  const leadHtml = `
    <h2>New SMB snapshot lead</h2>
    <p><strong>Name:</strong> ${escapeHtml(name)}</p>
    <p><strong>Email:</strong> ${escapeHtml(email)}</p>
    <p><strong>Business:</strong> ${escapeHtml(business) || "—"}</p>
    <p><strong>Qualification:</strong> ${escapeHtml(tier)} (score ${score})</p>
    <h3>Interview transcript</h3>
    <table>${transcriptRows}</table>
  `;

  const res = await sendPostmark(token, {
    From: FROM_ADDRESS,
    To: SALES_EMAIL,
    ReplyTo: email,
    Subject: `SMB snapshot lead — ${name}${business ? ` (${business})` : ""} · ${tier}`,
    HtmlBody: leadHtml,
    MessageStream: "outbound",
  });

  if (!res.ok) {
    console.error("Postmark snapshot lead send failed", res.status, await res.text());
    return {
      status: "error",
      message: "We couldn't save your snapshot. Email sam@joinstash.ai directly.",
    };
  }

  return { status: "ok" };
}
