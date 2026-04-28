"use server";

const SALES_EMAIL = "sam@joinstash.ai";
const FROM_ADDRESS = "Stash <notifications@joinstash.ai>";

export type ContactSalesState = {
  status: "idle" | "ok" | "error";
  message?: string;
};

export async function submitContactSales(
  _prev: ContactSalesState,
  formData: FormData,
): Promise<ContactSalesState> {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const company = String(formData.get("company") ?? "").trim();
  const teamSize = String(formData.get("teamSize") ?? "").trim();
  const message = String(formData.get("message") ?? "").trim();

  if (!name || !email) {
    return { status: "error", message: "Name and work email are required." };
  }
  if (!email.includes("@")) {
    return { status: "error", message: "Please enter a valid email address." };
  }

  const token = process.env.POSTMARK_SERVER_TOKEN;
  if (!token) {
    console.error("POSTMARK_SERVER_TOKEN is not set; cannot deliver contact-sales submission", {
      name,
      email,
      company,
      teamSize,
    });
    return {
      status: "error",
      message: "Sales inbox is not configured yet. Email sam@joinstash.ai directly.",
    };
  }

  const leadHtml = `
    <h2>New demo request</h2>
    <p><strong>Name:</strong> ${escapeHtml(name)}</p>
    <p><strong>Email:</strong> ${escapeHtml(email)}</p>
    <p><strong>Company:</strong> ${escapeHtml(company) || "—"}</p>
    <p><strong>Team size:</strong> ${escapeHtml(teamSize) || "—"}</p>
    <p><strong>Message:</strong></p>
    <p>${escapeHtml(message).replace(/\n/g, "<br/>") || "—"}</p>
  `;

  const confirmationHtml = `
    <p>Hi ${escapeHtml(name.split(/\s+/)[0] || name)},</p>
    <p>Thanks for reaching out about Stash — we got your demo request and someone from our team will be in touch within one business day to set up a 30-minute walkthrough.</p>
    <p>If you have anything to add in the meantime, just reply to this email.</p>
    <p>— The Stash team<br/><a href="https://joinstash.ai">joinstash.ai</a></p>
  `;

  const [leadRes, confirmRes] = await Promise.all([
    sendPostmark(token, {
      From: FROM_ADDRESS,
      To: SALES_EMAIL,
      ReplyTo: email,
      Subject: `Demo request — ${name}${company ? ` (${company})` : ""}`,
      HtmlBody: leadHtml,
      MessageStream: "outbound",
    }),
    sendPostmark(token, {
      From: FROM_ADDRESS,
      To: email,
      ReplyTo: SALES_EMAIL,
      Subject: "Thanks for reaching out to Stash",
      HtmlBody: confirmationHtml,
      MessageStream: "outbound",
    }),
  ]);

  if (!leadRes.ok) {
    console.error("Postmark lead send failed", leadRes.status, await leadRes.text());
    return {
      status: "error",
      message: "We couldn't send your request. Please email sam@joinstash.ai.",
    };
  }
  if (!confirmRes.ok) {
    console.error("Postmark confirmation send failed", confirmRes.status, await confirmRes.text());
  }

  return {
    status: "ok",
    message: "Thanks — we'll be in touch within one business day. Check your inbox for a confirmation.",
  };
}

type PostmarkPayload = {
  From: string;
  To: string;
  ReplyTo?: string;
  Subject: string;
  HtmlBody: string;
  MessageStream: string;
};

function sendPostmark(token: string, payload: PostmarkPayload) {
  return fetch("https://api.postmarkapp.com/email", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Postmark-Server-Token": token,
    },
    body: JSON.stringify(payload),
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
