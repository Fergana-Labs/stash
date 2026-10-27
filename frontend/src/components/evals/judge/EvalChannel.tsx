"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type ReactNode } from "react";
import { ArrowUp, FileText, Loader2, Paperclip, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
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

/** The eval's channel, like a Slack channel: the person's posts run down the middle, and the
 * agent, like a bot, only ever replies in a post's thread, and only when it has something to
 * say. Threads stay folded behind their reply count until opened. */
export default function EvalChannel({ evalId, messages, onSend, onLabel, onRemove }: {
  evalId: string;
  messages: EvalMessage[];
  onSend: (send: Send, onProgress: (sent: number) => void) => Promise<void>;
  onLabel: (exampleId: string, label: EvalLabel | null) => Promise<void>;
  onRemove: (exampleId: string) => Promise<void>;
}) {
  const actions = useMemo<AttachmentActions>(() => ({ label: onLabel, remove: onRemove }), [onLabel, onRemove]);
  const [over, setOver] = useState(false);
  const [dropped, setDropped] = useState<File[]>([]);
  const list = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const { top, replies } = useMemo(() => {
    const replies = new Map<string, EvalMessage[]>();
    const top: EvalMessage[] = [];
    for (const m of messages) {
      if (m.thread_id) replies.set(m.thread_id, [...(replies.get(m.thread_id) ?? []), m]);
      else top.push(m);
    }
    return { top, replies };
  }, [messages]);
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
    <section aria-label="Channel" className={cn("relative flex min-h-[420px] flex-col rounded border border-border lg:min-h-0 lg:flex-1", over && "border-brand-500")}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false); }} onDrop={drop}>
      <div ref={list} className="scroll-thin flex-1 space-y-1 px-3 py-3 lg:overflow-y-auto">
        {top.length === 0
          ? <UploadBox title="Drop screenshots of good and bad agent work" disabled={false} onFiles={setDropped} />
          : top.map((m) => <Message key={m.id} evalId={evalId} message={m} replies={replies.get(m.id) ?? []} onSend={onSend} actions={actions} />)}
        <div ref={bottom} />
      </div>
      <div className="sticky bottom-0 border-t border-border bg-background p-2">
        <Composer placeholder="Message" files={dropped} onFilesTaken={() => setDropped([])} onSend={(text, files, progress) => onSend({ text, files }, progress)} />
      </div>
    </section>
  );
}

function Author({ message }: { message: EvalMessage }) {
  const agent = message.author === "agent";
  return <div className="flex items-baseline gap-2 text-[12px]">
    <span className={cn("font-semibold", agent ? "text-violet-600 dark:text-violet-400" : "text-blue-600 dark:text-blue-400")}>{agent ? "Agent" : "You"}</span>
    {message.data.via && <span className="text-muted-foreground">via {message.data.via}</span>}
    <time className="text-muted-foreground" dateTime={message.created_at}>{relativeTime(message.created_at)}</time>
  </div>;
}

function Message({ evalId, message, replies, onSend, actions }: {
  evalId: string;
  message: EvalMessage;
  replies: EvalMessage[];
  onSend: (send: Send, onProgress: (sent: number) => void) => Promise<void>;
  actions: AttachmentActions;
}) {
  // Folded like a Slack thread: the reply count, who replied last and when. When the agent's
  // last word is a question, it's waiting on the person, so the count stands out; a rubric
  // report isn't waiting on anyone.
  const [open, setOpen] = useState(false);
  const last = replies.at(-1);
  const waiting = !!last && last.author === "agent" && last.kind === "message"
    && (!!last.data.choices?.length || !!last.data.about || last.text.trim().endsWith("?"));
  const count = replies.length === 1 ? "1 reply" : `${replies.length} replies`;
  return (
    <article className="group rounded px-1 py-1.5 hover:bg-surface/40">
      <Author message={message} />
      <Body evalId={evalId} message={message} actions={actions} />
      {last && (
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
          className="mt-1 flex items-baseline gap-2 text-[12px] hover:underline">
          <span className={cn("text-brand-600", waiting && !open && "font-semibold")}>{open ? "Hide replies" : count}</span>
          {!open && <span className="text-muted-foreground">{last.author === "agent" ? "Agent" : "You"} {relativeTime(last.created_at)}</span>}
        </button>
      )}
      {(open || replies.length === 0) && (
        <Thread evalId={evalId} message={message} replies={replies} open={open} onSend={onSend} actions={actions} />
      )}
    </article>
  );
}

function Body({ evalId, message, actions }: { evalId: string; message: EvalMessage; actions: AttachmentActions }) {
  if (message.kind === "rubric") return <RubricUpdate message={message} />;
  return <>
    {message.text && <p className="mt-0.5 whitespace-pre-wrap text-[13px] leading-5">{message.text}</p>}
    {message.about && <div className="mt-1 w-16"><Attachment evalId={evalId} attachment={message.about} actions={actions} /></div>}
    {message.attachments.length > 0 && (
      <div className="mt-1.5 grid grid-cols-[repeat(auto-fill,minmax(88px,1fr))] gap-1.5">
        {message.attachments.map((a) => <Attachment key={a.example_id} evalId={evalId} attachment={a} actions={actions} />)}
      </div>
    )}
    {message.data.uploading && <p role="status" className="mt-1 text-[12px] text-muted-foreground">Uploading</p>}
  </>;
}

const VERB: Record<string, string> = { add: "Added", tighten: "Tightened", fix: "Fixed", point: "Pointed", remove: "Removed", request: "Changed", scoring: "Now scored by" };

function RubricUpdate({ message }: { message: EvalMessage }) {
  const changes = (message.data.changes ?? []).filter((c) => c.trait);
  return <div className="mt-1 rounded border border-border px-2.5 py-2 text-[13px]">
    <p className="leading-5">{message.text}</p>
    {changes.length > 0 && (
      <ul className="mt-1 space-y-0.5 text-[12px]">
        {changes.map((c, i) => <li key={i}><span className="font-medium">{VERB[c.kind] ?? c.kind} {c.trait}</span>{c.why && <span className="text-muted-foreground">: {c.why}</span>}</li>)}
      </ul>
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
  // The reason usually repeats what the message says, so it shows on hover, not under each file.
  return <figure className="group/attachment relative m-0 min-w-0" title={attachment.note || undefined}>
    {image
      ? <FileThumb path={evalExampleFilePath(evalId, attachment.example_id, 0)} alt={attachment.name} className="aspect-square w-full" />
      : <div title={attachment.name} className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-sm border border-border px-1 text-center text-[10px] text-muted-foreground"><FileText className="size-4" /><span className="line-clamp-2 break-all">{attachment.name}</span></div>}
    <button type="button" aria-label={`Remove ${attachment.name}`} title="Remove from the eval" disabled={saving} onClick={() => void remove()}
      className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-sm border border-border bg-background/95 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 disabled:opacity-60 group-hover/attachment:opacity-100 max-sm:opacity-100">
      <X className="size-3" />
    </button>
    <figcaption className="mt-1">
      <div role="group" aria-label={`Label ${attachment.name}`} className="inline-flex h-5 overflow-hidden rounded-sm border border-border text-[10px]">
        {(["good", "bad"] as const).map((label) => (
          <button key={label} type="button" disabled={saving} aria-pressed={attachment.label === label} onClick={() => void set(label)}
            className={cn("px-1.5 leading-none transition-colors disabled:opacity-60", attachment.label === label
              ? label === "good" ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
              : "text-muted-foreground hover:bg-surface")}>
            {label === "good" ? "Good" : "Bad"}
          </button>
        ))}
      </div>
      {attachment.held_out && <div className="mt-0.5 text-[10px] text-muted-foreground">Held out</div>}
    </figcaption>
  </figure>;
}

function Thread({ evalId, message, replies, open, onSend, actions }: {
  evalId: string;
  message: EvalMessage;
  replies: EvalMessage[];
  open: boolean;
  onSend: (send: Send, onProgress: (sent: number) => void) => Promise<void>;
  actions: AttachmentActions;
}) {
  const [replying, setReplying] = useState(false);
  const last = replies.at(-1);
  const choices = last?.author === "agent" ? last.data.choices ?? [] : [];
  const reply = (text: string, files: File[] = [], progress: (sent: number) => void = () => {}) => onSend({ text, files, threadId: message.id }, progress);
  if (!open) {
    // No replies yet: a quiet "Reply" on hover, like a chat thread.
    return replying
      ? <div className="mt-1.5 border-l-2 border-border pl-3"><ThreadComposer onSend={reply} onCancel={() => setReplying(false)} /></div>
      : <button type="button" onClick={() => setReplying(true)} className="mt-0.5 text-[12px] text-muted-foreground opacity-0 hover:underline focus:opacity-100 group-hover:opacity-100">Reply</button>;
  }
  return <div className="mt-1.5 space-y-1.5 border-l-2 border-border pl-3">
    {replies.map((r) => <div key={r.id}><Author message={r} /><Body evalId={evalId} message={r} actions={actions} /></div>)}
    {choices.length > 0 && <div className="flex flex-wrap gap-1.5">{choices.map((c) => <ChoiceButton key={c} onClick={() => reply(c)}>{c}</ChoiceButton>)}</div>}
    <ThreadComposer onSend={reply} />
  </div>;
}

function ChoiceButton({ onClick, children }: { onClick: () => Promise<void>; children: ReactNode }) {
  const [sending, setSending] = useState(false);
  return <button type="button" disabled={sending} onClick={() => { setSending(true); void onClick().finally(() => setSending(false)); }}
    className="h-6 rounded border border-border px-2 text-[12px] hover:bg-surface disabled:opacity-60">{children}</button>;
}

function ThreadComposer({ onSend, onCancel }: { onSend: (text: string, files: File[], progress: (sent: number) => void) => Promise<void>; onCancel?: () => void }) {
  return <Composer compact placeholder="Reply" onSend={onSend} onEscape={onCancel} autoFocus={!!onCancel} />;
}

function Composer({ placeholder, compact = false, files: given = [], onFilesTaken, onSend, onEscape, autoFocus = false }: {
  placeholder: string;
  compact?: boolean;
  files?: File[];
  onFilesTaken?: () => void;
  onSend: (text: string, files: File[], progress: (sent: number) => void) => Promise<void>;
  onEscape?: () => void;
  autoFocus?: boolean;
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
    <div className={cn("flex items-end gap-1.5 rounded border border-border bg-background px-2 focus-within:border-foreground/40", compact ? "py-1" : "py-1.5")}>
      <button type="button" aria-label="Attach files" disabled={sending} onClick={() => picker.current?.click()} className="mb-0.5 text-muted-foreground hover:text-foreground disabled:opacity-50"><Paperclip className="size-4" /></button>
      <input ref={picker} type="file" multiple className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => { const picked = Array.from(e.target.files ?? []); if (picked.length) setFiles((prev) => [...prev, ...picked]); e.target.value = ""; }} />
      <textarea ref={area} rows={1} value={text} placeholder={placeholder} aria-label={placeholder} disabled={sending} autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)} onPaste={paste}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); }
          if (e.key === "Escape") onEscape?.();
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
