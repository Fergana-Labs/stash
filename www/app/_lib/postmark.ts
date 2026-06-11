// Shared Postmark sender for lead-capture server actions
// (contact-sales and the message-test survey).

export type PostmarkPayload = {
  From: string;
  To: string;
  ReplyTo?: string;
  Subject: string;
  HtmlBody: string;
  MessageStream: string;
};

export function sendPostmark(token: string, payload: PostmarkPayload) {
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

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
