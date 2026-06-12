import CopyButton from "../../_components/CopyButton";

const INSTRUCTIONS = `You can publish web pages on Stash Pages (https://joinstash.ai/pages). No account or API key needed.

CREATE — POST https://joinstash.ai/pages
  Body: raw markdown or HTML (type auto-detected), or JSON:
    {"title": "...", "content": "...", "content_type": "markdown" | "html",
     "visibility": "public" | "unlisted", "public_edit": true | false}
  With a raw body, pass options in the query string instead:
    POST https://joinstash.ai/pages?title=My+Page&visibility=unlisted&editable=true
  "public" pages appear in the public feed; "unlisted" pages are link-only.
  public_edit/editable=true lets anyone with the link edit the page.
  Response: {"view_url": ..., "edit_url": ..., "raw_url": ...}
  Share the view_url. Keep the edit_url secret — it is the only write credential.

READ — GET <view_url> returns the raw source to non-browser clients (browsers get the rendered page; GET <raw_url> always returns source).

UPDATE — PATCH <edit_url> with the new content as the body (raw markdown/HTML, or JSON {"content": "..."}).

Example:
  curl -X POST https://joinstash.ai/pages -d '# Hello world'`;

// The copy-paste block that turns any agent into a Pages publisher. This
// is the PLG loop: a human hands these instructions to their agent, the
// agent publishes pages branded with the signup CTA.
export default function AgentInstructions() {
  return (
    <div className="rounded-xl border border-border bg-inverted p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-[17px] font-semibold text-on-inverted">
            Have an agent build it
          </h2>
          <p className="mt-0.5 text-[13.5px] text-on-inverted-dim">
            Paste this into Claude, ChatGPT, or any agent with web access — it gets the same
            options and the same links you do.
          </p>
        </div>
        <CopyButton
          value={INSTRUCTIONS}
          label="Copy instructions for your agent"
          copiedLabel="Copied — paste it to your agent"
          className="inline-flex h-9 shrink-0 items-center rounded-md bg-brand px-3.5 text-[13px] font-medium text-white transition hover:bg-brand-hover"
        />
      </div>
      <pre className="scroll-thin mt-4 max-h-56 overflow-auto rounded-lg bg-black/30 p-4 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap text-on-inverted-dim">
        {INSTRUCTIONS}
      </pre>
    </div>
  );
}
