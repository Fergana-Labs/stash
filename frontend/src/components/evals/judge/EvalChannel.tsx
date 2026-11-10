"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type ReactNode } from "react";
import { ArrowUp, FileText, Loader2, Paperclip, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/components/reward-models/rm-text";
import FileThumb from "./FileThumb";
import UploadBox from "./UploadBox";
import { droppedFiles } from "./dropped-files";
import { evalExampleFilePath, type EvalAttachment, type EvalLabel, type EvalMessage } from "@/lib/evals-api";

export interface Send { text: string; files: File[]; threadId?: string }
/** What the person can do to a dropped file from the channel. */
interface AttachmentActions {
  label: (exampleId: string, label: EvalLabel | null) => Promise<void>;
  remove: (exampleId: string) => Promise<void>;
}

/** The eval wizard as one conversation, laid out like a chat: the person's messages on the
 * right, the agent's on the left, nobody named, in the order they were sent, and one box at
 * the bottom that continues it. What the person types
 * answers where the conversation is (it is sent as a reply to the latest exchange, so the
 * agent knows what it is about); files start a new exchange. When the agent's last message
 * offers choices, they are buttons above the box. */
export default function EvalChannel({ evalId, messages, reading = false, onSend, onLabel, onRemove }: {
  evalId: string;
  messages: EvalMessage[];
  /** The agent is reading the conversation: while a message is unread, it shows as typing. */
  reading?: boolean;
  onSend: (send: Send, onProgress: (sent: number) => void) => Promise<void>;
  onLabel: (exampleId: string, label: EvalLabel | null) => Promise<void>;
  onRemove: (exampleId: string) => Promise<void>;
}) {
  const actions = useMemo<AttachmentActions>(() => ({ label: onLabel, remove: onRemove }), [onLabel, onRemove]);
  const [over, setOver] = useState(false);
  const [dropped, setDropped] = useState<File[]>([]);
  const list = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const ordered = useMemo(() => [...messages].sort((a, b) => a.created_at.localeCompare(b.created_at)), [messages]);
  const last = ordered.at(-1);
  // The exchange the conversation is in: the latest message's, or that message if it began one.
  const thread = last ? last.thread_id ?? last.id : undefined;
  const typing = reading && messages.some((m) => m.unread);
  const choices = last?.author === "agent" ? last.data.choices ?? [] : [];
  const send = (text: string, files: File[], progress: (sent: number) => void) =>
    onSend(files.length || !thread ? { text, files } : { text, files, threadId: thread }, progress);
  const lastId = messages.at(-1)?.id;
  const pinned = useRef(true);
  useEffect(() => {
    // Wide screens scroll the message list itself; narrow ones scroll the page to it.
    const el = list.current;
    if (el && el.scrollHeight > el.clientHeight + 1) el.scrollTop = el.scrollHeight;
    else bottom.current?.scrollIntoView({ block: "nearest" });
    pinned.current = true;
  }, [lastId]);
  useEffect(() => {
    // Images that finish loading grow the list; someone reading the latest stays at the latest.
    const el = list.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const onScroll = () => { pinned.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 80; };
    const observer = new ResizeObserver(() => { if (pinned.current) el.scrollTop = el.scrollHeight; });
    for (const child of Array.from(el.children)) observer.observe(child);
    el.addEventListener("scroll", onScroll);
    return () => { observer.disconnect(); el.removeEventListener("scroll", onScroll); };
  }, [messages]);

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    void droppedFiles(event.dataTransfer).then((files) => { if (files.length) setDropped(files); });
  };
  return (
    <section aria-label="Eval wizard" className={cn("relative flex min-h-[420px] flex-col rounded border border-border lg:min-h-0 lg:flex-1", over && "border-brand-500")}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false); }} onDrop={drop}>
      <div ref={list} className="scroll-thin flex-1 space-y-1 px-3 py-3 lg:overflow-y-auto">
        {ordered.length === 0
          ? <UploadBox title="Drop screenshots of good and bad agent work" disabled={false} onFiles={setDropped} />
          : ordered.map((m) => <Message key={m.id} evalId={evalId} message={m} actions={actions} />)}
        {typing && <div className="py-1.5"><Typing /></div>}
        <div ref={bottom} />
      </div>
      <div className="sticky bottom-0 border-t border-border bg-background p-2">
        {choices.length > 0 && <div className="mb-1.5 flex flex-wrap gap-1.5">{choices.map((c) => <ChoiceButton key={c} onClick={() => send(c, [], () => {})}>{c}</ChoiceButton>)}</div>}
        <Composer placeholder="Message" files={dropped} onFilesTaken={() => setDropped([])} onSend={send} />
      </div>
    </section>
  );
}

/** The agent is working on a reply: three dots that pulse in turn. */
function Typing() {
  return <div role="status" aria-label="Agent is replying" className="flex h-5 items-center gap-1">
    {[0, 200, 400].map((delay) => <span key={delay} aria-hidden style={{ animationDelay: `${delay}ms` }}
      className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-duration:1.2s] motion-reduce:animate-none" />)}
  </div>;
}

/** One message, with no name on it: the person's sit on the right in a dark bubble with their
 * files above it, the agent's are plain text on the left. When it was sent shows on hover. */
function Message({ evalId, message, actions }: { evalId: string; message: EvalMessage; actions: AttachmentActions }) {
  const sent = new Date(message.created_at).toLocaleString();
  if (message.author === "agent") return <article aria-label="Agent message" title={sent} className="py-1.5 pr-12"><Body evalId={evalId} message={message} actions={actions} /></article>;
  return <article aria-label="Your message" title={sent} className="flex flex-col items-end gap-1.5 py-1.5 pl-12">
    {message.data.via && <span className="text-[11px] text-muted-foreground">via {message.data.via}</span>}
    {message.attachments.length > 0 && (
      <div className="flex flex-wrap justify-end gap-1.5">
        {message.attachments.map((a) => <Attachment key={a.example_id} evalId={evalId} attachment={a} actions={actions} />)}
      </div>
    )}
    {message.text && <p className="m-0 max-w-full whitespace-pre-wrap rounded bg-foreground px-3 py-1.5 text-[13px] leading-5 text-background">{message.text}</p>}
    {message.data.uploading && <p role="status" className="m-0 text-[12px] text-muted-foreground">Uploading</p>}
  </article>;
}

function Body({ evalId, message, actions }: { evalId: string; message: EvalMessage; actions: AttachmentActions }) {
  if (message.kind === "rubric") return <RubricUpdate evalId={evalId} message={message} />;
  return <>
    {message.text && <p className="m-0 whitespace-pre-wrap text-[13px] leading-5">{message.text}</p>}
    {message.about && <div className="mt-1 flex"><Attachment evalId={evalId} attachment={message.about} actions={actions} /></div>}
    {message.attachments.length > 0 && (
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {message.attachments.map((a) => <Attachment key={a.example_id} evalId={evalId} attachment={a} actions={actions} />)}
      </div>
    )}
    {message.data.uploading && <p role="status" className="mt-1 text-[12px] text-muted-foreground">Uploading</p>}
  </>;
}

const VERB: Record<string, string> = { add: "Added", tighten: "Tightened", fix: "Fixed", point: "Pointed", remove: "Removed", request: "Changed", scoring: "Now scored by" };

function RubricUpdate({ evalId, message }: { evalId: string; message: EvalMessage }) {
  const changes = (message.data.changes ?? []).filter((c) => c.trait);
  return <div className="text-[13px]">
    <p className="m-0 leading-5">{message.text}</p>
    {changes.length > 0 && (
      <ul className="mt-1 space-y-0.5 text-[12px]">
        {changes.map((c, i) => <li key={i}><span className="font-medium">{VERB[c.kind] ?? c.kind} {c.trait}</span>{c.why && <span className="text-muted-foreground">: {c.why}</span>}</li>)}
      </ul>
    )}
    {message.data.proposal !== undefined && (
      <Link href={`/reward-models/evals/${evalId}/changes/${message.data.proposal}`} className="mt-1.5 inline-flex h-6 items-center rounded border border-border px-2 text-[12px] text-foreground no-underline hover:bg-surface">Review change request #{message.data.proposal}</Link>
    )}
  </div>;
}

function Attachment({ evalId, attachment, actions }: { evalId: string; attachment: EvalAttachment; actions: AttachmentActions }) {
  const [saving, setSaving] = useState(false);
  const set = async (label: EvalLabel) => {
    setSaving(true);
    try { await actions.label(attachment.example_id, attachment.label === label ? null : label); } finally { setSaving(false); }
  };
  const remove = async () => {
    setSaving(true);
    try { await actions.remove(attachment.example_id); } catch { setSaving(false); }
  };
  const image = attachment.content_type.startsWith("image/");
  // A file as a chip, the way a chat shows an attachment: its icon or a small preview, its
  // name (which opens the example), its label, and an X on hover. The reason usually repeats
  // what the message says, so it shows on hover, not on each file.
  return <figure className="group/attachment relative m-0 inline-flex h-7 max-w-full items-center gap-1.5 rounded border border-border bg-background pr-1 pl-1.5 text-[12px]" title={attachment.note || undefined}>
    {image
      ? <FileThumb path={evalExampleFilePath(evalId, attachment.example_id, 0)} alt={attachment.name} className="size-5 shrink-0" />
      : <FileText aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />}
    <figcaption className="contents">
      <Link href={`/reward-models/evals/${evalId}/examples/${attachment.example_id}`} title={attachment.name} className="min-w-0 max-w-56 truncate text-foreground no-underline hover:underline">{attachment.name}</Link>
      {attachment.held_out && <span className="shrink-0 text-[10px] text-muted-foreground">Held out</span>}
      <div role="group" aria-label={`Label ${attachment.name}`} className="inline-flex h-5 shrink-0 overflow-hidden rounded-sm border border-border text-[10px]">
        {(["good", "bad"] as const).map((label) => (
          <button key={label} type="button" disabled={saving} aria-pressed={attachment.label === label} onClick={() => void set(label)}
            className={cn("px-1.5 leading-none transition-colors disabled:opacity-60", attachment.label === label
              ? "bg-surface font-medium text-foreground"
              : "text-muted-foreground hover:bg-surface")}>
            {label === "good" ? "Good" : "Bad"}
          </button>
        ))}
      </div>
    </figcaption>
    <button type="button" aria-label={`Remove ${attachment.name}`} title="Remove from the eval" disabled={saving} onClick={() => void remove()}
      className="absolute -top-1.5 -right-1.5 flex size-4 items-center justify-center rounded-sm border border-border bg-background text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 disabled:opacity-60 group-hover/attachment:opacity-100 max-sm:opacity-100">
      <X className="size-3" />
    </button>
  </figure>;
}

function ChoiceButton({ onClick, children }: { onClick: () => Promise<void>; children: ReactNode }) {
  const [sending, setSending] = useState(false);
  return <button type="button" disabled={sending} onClick={() => { setSending(true); void onClick().finally(() => setSending(false)); }}
    className="h-6 rounded border border-border px-2 text-[12px] hover:bg-surface disabled:opacity-60">{children}</button>;
}

function Composer({ placeholder, files: given = [], onFilesTaken, onSend }: {
  placeholder: string;
  files?: File[];
  onFilesTaken?: () => void;
  onSend: (text: string, files: File[], progress: (sent: number) => void) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!given.length) return;
    setFiles((prev) => [...prev, ...given]);
    onFilesTaken?.();
    area.current?.focus();
  }, [given, onFilesTaken]);
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);
  const previews = useMemo(() => files.map((f) => (f.type.startsWith("image/") ? URL.createObjectURL(f) : null)), [files]);
  useEffect(() => () => previews.forEach((u) => u && URL.revokeObjectURL(u)), [previews]);

  async function send() {
    if (sending || (!text.trim() && !files.length)) return;
    setSending(true); setError("");
    const total = files.length;
    if (total) setStatus(`Uploading 0/${total}`);
    try {
      await onSend(text.trim(), files, (sent) => setStatus(`Uploading ${sent}/${total}`));
      setText(""); setFiles([]);
    } catch (e) { setError(errorMessage(e)); } finally { setSending(false); setStatus(""); }
  }
  const paste = (event: ClipboardEvent) => {
    const pasted = Array.from(event.clipboardData.files);
    if (pasted.length) { event.preventDefault(); setFiles((prev) => [...prev, ...pasted]); }
  };
  return <div>
    {files.length > 0 && (
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        {files.map((f, i) => (
          <div key={`${f.name}-${i}`} className="relative size-12 overflow-hidden rounded-sm border border-border" title={f.name}>
            {previews[i]
              // eslint-disable-next-line @next/next/no-img-element -- local previews of files not yet sent
              ? <img src={previews[i]!} alt={f.name} className="size-full object-cover" />
              : <span className="flex size-full items-center justify-center p-0.5 text-center text-[9px] leading-tight text-muted-foreground">{f.name}</span>}
            {!sending && <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}
              className="absolute right-0 top-0 rounded-bl-sm bg-background/90 p-0.5"><X className="size-2.5" /></button>}
          </div>
        ))}
      </div>
    )}
    <div className="flex items-end gap-1.5 rounded border border-border bg-background px-2 py-1.5 focus-within:border-foreground/40">
      <button type="button" aria-label="Attach files" disabled={sending} onClick={() => picker.current?.click()} className="mb-0.5 text-muted-foreground hover:text-foreground disabled:opacity-50"><Paperclip className="size-4" /></button>
      <input ref={picker} type="file" multiple className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => { const picked = Array.from(e.target.files ?? []); if (picked.length) setFiles((prev) => [...prev, ...picked]); e.target.value = ""; }} />
      <textarea ref={area} rows={1} value={text} placeholder={placeholder} aria-label={placeholder} disabled={sending}
        onChange={(e) => setText(e.target.value)} onPaste={paste}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); }
        }}
        className="max-h-[200px] min-w-0 flex-1 resize-none bg-transparent py-0.5 text-[13px] leading-5 outline-none disabled:opacity-60" />
      <button type="button" aria-label="Send" disabled={sending || (!text.trim() && !files.length)} onClick={() => void send()}
        className="mb-0.5 flex size-6 items-center justify-center rounded bg-foreground text-background disabled:opacity-30">
        {sending ? <Loader2 className="size-3.5 animate-spin" /> : <ArrowUp className="size-3.5" />}
      </button>
    </div>
    {(status || error) && <p role={error ? "alert" : "status"} className={cn("mt-1 text-[12px]", error ? "text-destructive" : "text-muted-foreground")}>{error || status}</p>}
  </div>;
}
