"use client";

import { useEffect, useRef, useState } from "react";

import { submitSnapshotLead } from "./actions";

// The assessment interview as a real chat. One deterministic routing question
// (what AI do you use today?) — agent users get the interview skill as a
// friendly install card; everyone else talks to the model, which runs the
// interview from /api/smb-chat and ends by producing the snapshot report.

const AGENT_TOOLS = ["Claude Code", "Codex", "Cowork"];
const AI_OPTIONS = [...AGENT_TOOLS, "ChatGPT", "None yet"];

type Report = {
  business_type: string;
  goal: string;
  score: number;
  tier: string;
  hours_week: number;
  value_month: number;
  findings: { title: string; before: string; after: string; hours: string }[];
  tool: { name: string; why: string; cost: string; setup: string };
};

type ApiReply = {
  message: string;
  done?: boolean;
  report?: Report;
};

type Bubble =
  | { kind: "text"; from: "agent" | "you"; text: string }
  | { kind: "skill"; tool: string };

type ApiMessage = { role: "user" | "assistant"; content: string };

const INTRO =
  "Hey — I'll ask a few quick questions, about three minutes, then hand you a one-page snapshot.";
const FIRST_QUESTION = "First one: what AI do you use today?";

function sanitizeReport(r: Report): Report {
  return {
    ...r,
    score: Math.max(0, Math.min(100, Math.round(r.score))),
    hours_week: Math.max(1, Math.min(20, Math.round(r.hours_week))),
    value_month: Math.max(0, Math.floor(r.value_month)),
    findings: r.findings.slice(0, 3),
  };
}

export default function AssessmentChat() {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [typing, setTyping] = useState(false);
  const [mode, setMode] = useState<"routing" | "chat" | "skill" | "contact">("routing");
  const [apiMessages, setApiMessages] = useState<ApiMessage[]>([]);
  const [options, setOptions] = useState<string[]>(AI_OPTIONS);
  const [draft, setDraft] = useState("");
  const [chatError, setChatError] = useState(false);
  const [contact, setContact] = useState({ name: "", email: "", business: "" });
  const [pendingReport, setPendingReport] = useState<Report | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sendState, setSendState] = useState<"idle" | "sending">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    const t = timers.current;
    setTyping(true);
    t.push(
      setTimeout(() => setBubbles([{ kind: "text", from: "agent", text: INTRO }]), 550),
      setTimeout(() => {
        setBubbles((b) => [...b, { kind: "text", from: "agent", text: FIRST_QUESTION }]);
        setTyping(false);
      }, 1100),
    );
    return () => t.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [bubbles, typing, report, mode]);

  async function callChat(messages: ApiMessage[]) {
    setTyping(true);
    setChatError(false);
    const res = await fetch("/api/smb-chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    if (!res.ok) {
      setTyping(false);
      setChatError(true);
      return;
    }
    const { reply, raw } = (await res.json()) as { reply: ApiReply; raw: string };
    setApiMessages([...messages, { role: "assistant", content: raw }]);
    setBubbles((b) => [...b, { kind: "text", from: "agent", text: reply.message }]);
    setTyping(false);
    if (reply.done && reply.report) {
      setPendingReport(sanitizeReport(reply.report));
      setMode("contact");
    }
  }

  function sendToChat(text: string) {
    setBubbles((b) => [...b, { kind: "text", from: "you", text }]);
    setDraft("");
    const messages: ApiMessage[] = [...apiMessages, { role: "user", content: text }];
    setApiMessages(messages);
    void callChat(messages);
  }

  function answerRouting(value: string) {
    setBubbles((b) => [...b, { kind: "text", from: "you", text: value }]);
    setOptions([]);
    if (AGENT_TOOLS.includes(value)) {
      setMode("skill");
      setTyping(true);
      timers.current.push(
        setTimeout(() => {
          setBubbles((b) => [
            ...b,
            {
              kind: "text",
              from: "agent",
              text: `You're ahead of most businesses. Since you already use ${value}, you can skip the questions — take the interview itself and run it at home. It works on your own files and history, and nothing leaves your computer.`,
            },
            { kind: "skill", tool: value },
          ]);
          setTyping(false);
        }, 700),
      );
      return;
    }
    setMode("chat");
    const seed: ApiMessage[] = [
      {
        role: "user",
        content: `The AI I use today: ${value}. I'm ready — ask me your first question.`,
      },
    ];
    setApiMessages(seed);
    void callChat(seed);
  }

  function retryChat() {
    void callChat(apiMessages);
  }

  async function generate() {
    if (!contact.name.trim() || !contact.email.includes("@")) {
      setErrorMessage("Add your name and a valid email to get the report.");
      return;
    }
    if (!pendingReport) return;
    setErrorMessage("");
    setSendState("sending");
    const transcript: [string, string][] = bubbles
      .filter((b): b is Extract<Bubble, { kind: "text" }> => b.kind === "text")
      .map((b) => [b.from === "you" ? "Visitor" : "Stash", b.text]);
    const result = await submitSnapshotLead({
      name: contact.name,
      email: contact.email,
      business: contact.business,
      score: pendingReport.score,
      tier: pendingReport.tier,
      transcript,
    });
    setSendState("idle");
    if (result.status === "error") {
      setErrorMessage(result.message ?? "Something went wrong.");
      return;
    }
    setReport(pendingReport);
  }

  if (report) {
    return <SnapshotReport report={report} contact={contact} />;
  }

  return (
    <div className="overflow-hidden rounded-[14px] border border-border bg-background shadow-[var(--shadow-card)]">
      <div ref={scrollRef} className="max-h-[460px] space-y-3 overflow-y-auto p-5">
        {bubbles.map((b, i) =>
          b.kind === "skill" ? (
            <SkillDrop key={i} tool={b.tool} />
          ) : (
            <div key={i} className={b.from === "you" ? "flex justify-end" : "flex"}>
              <div
                className={
                  b.from === "you"
                    ? "max-w-[80%] rounded-[12px] rounded-br-[3px] bg-brand px-4 py-2.5 text-[14px] leading-[1.5] text-white"
                    : "max-w-[80%] rounded-[12px] rounded-bl-[3px] bg-raised px-4 py-2.5 text-[14px] leading-[1.5] text-ink"
                }
              >
                {b.text}
              </div>
            </div>
          ),
        )}
        {typing && (
          <div className="flex">
            <div className="rounded-[12px] rounded-bl-[3px] bg-raised px-4 py-3">
              <span className="typing-dots inline-flex gap-1">
                <i className="h-1.5 w-1.5 rounded-full bg-dim" />
                <i className="h-1.5 w-1.5 rounded-full bg-dim" />
                <i className="h-1.5 w-1.5 rounded-full bg-dim" />
              </span>
            </div>
          </div>
        )}
        {chatError && (
          <div className="flex">
            <div className="rounded-[12px] rounded-bl-[3px] border border-border bg-surface px-4 py-2.5 text-[13.5px] text-dim">
              Hit a snag on my end.{" "}
              <button onClick={retryChat} className="font-medium text-brand hover:underline">
                Try again
              </button>
            </div>
          </div>
        )}
      </div>

      {mode === "routing" && !typing && (
        <div className="border-t border-border-subtle p-5">
          <div className="flex flex-wrap gap-2">
            {options.map((o) => (
              <button
                key={o}
                onClick={() => answerRouting(o)}
                className="rounded-full border border-border bg-background px-4 py-2 text-[13.5px] text-ink transition hover:border-brand hover:text-brand"
              >
                {o}
              </button>
            ))}
          </div>
        </div>
      )}

      {mode === "chat" && (
        <div className="space-y-2.5 border-t border-border-subtle p-5">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim() && !typing) sendToChat(draft.trim());
            }}
            className="flex gap-2"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type your answer…"
              maxLength={500}
              className="h-11 flex-1 rounded-lg border border-border bg-background px-4 text-[14px] text-ink outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={typing || !draft.trim()}
              className="h-11 rounded-lg bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      )}

      {mode === "contact" && !typing && (
        <div className="space-y-2.5 border-t border-border-subtle p-5">
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <input
              value={contact.name}
              onChange={(e) => setContact((c) => ({ ...c, name: e.target.value }))}
              placeholder="Your name"
              className="h-11 rounded-lg border border-border bg-background px-4 text-[14px] text-ink outline-none focus:border-brand"
            />
            <input
              value={contact.email}
              onChange={(e) => setContact((c) => ({ ...c, email: e.target.value }))}
              placeholder="Email"
              type="email"
              className="h-11 rounded-lg border border-border bg-background px-4 text-[14px] text-ink outline-none focus:border-brand"
            />
            <input
              value={contact.business}
              onChange={(e) => setContact((c) => ({ ...c, business: e.target.value }))}
              placeholder="Business name"
              className="h-11 rounded-lg border border-border bg-background px-4 text-[14px] text-ink outline-none focus:border-brand"
            />
          </div>
          <button
            onClick={generate}
            disabled={sendState === "sending"}
            className="h-11 w-full rounded-lg bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover disabled:opacity-60"
          >
            {sendState === "sending" ? "Building your snapshot…" : "Show my snapshot →"}
          </button>
          {errorMessage && <p className="text-[13px] text-red-600">{errorMessage}</p>}
          <p className="text-[12px] text-muted">
            Your report renders right here. We&apos;ll also reach out about the full assessment
            — no spam, unsubscribe with one reply.
          </p>
        </div>
      )}

      <style>{`
        .typing-dots i { animation: typing-bounce 1.2s infinite; }
        .typing-dots i:nth-child(2) { animation-delay: 0.15s; }
        .typing-dots i:nth-child(3) { animation-delay: 0.3s; }
        @keyframes typing-bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
          30% { transform: translateY(-3px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

const INSTALL_COMMAND = `curl -fsSL https://joinstash.ai/smb/SKILL.md --create-dirs -o ~/.claude/skills/ai-assessment-interview/SKILL.md && curl -fsSL https://joinstash.ai/smb/report-template.html -o ~/.claude/skills/ai-assessment-interview/report-template.html`;

const BOOK_CALL_URL = "https://calendly.com/sam-ferganalabs/30min";

// The lead magnet for people already running an agent: a friendly three-step
// card — no terminal styling, one copy button hides the command.
function SkillDrop({ tool }: { tool: string }) {
  const [copied, setCopied] = useState(false);
  const isCowork = tool === "Cowork";

  function copy() {
    void navigator.clipboard.writeText(INSTALL_COMMAND);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="max-w-[94%] rounded-[12px] border border-border bg-surface p-5">
      <p className="font-display text-[15.5px] font-bold text-ink">
        The interview, as a file your AI can run
      </p>
      <ol className="mt-3 space-y-2.5">
        <StepItem n={1}>
          {isCowork ? (
            <>
              <a href="/smb/SKILL.md" download className="font-medium text-brand hover:underline">
                Download the skill file
              </a>{" "}
              and drag it into your Cowork session.
            </>
          ) : (
            <>
              Copy the setup line below and paste it into your terminal — or{" "}
              <a href="/smb/SKILL.md" download className="font-medium text-brand hover:underline">
                download the file
              </a>{" "}
              instead.
            </>
          )}
        </StepItem>
        <StepItem n={2}>
          Say: <span className="font-medium text-ink">&ldquo;run the assessment interview&rdquo;</span>
        </StepItem>
        <StepItem n={3}>
          Answer its questions like you would here — it writes the same one-page report, using
          your real files and history. Nothing leaves your computer.
        </StepItem>
      </ol>
      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        {!isCowork && (
          <button
            onClick={copy}
            className="inline-flex h-10 items-center rounded-lg border border-border bg-background px-4 text-[13.5px] font-medium text-ink transition hover:border-ink"
          >
            {copied ? "Copied ✓" : "Copy setup line"}
          </button>
        )}
        <a
          href={BOOK_CALL_URL}
          className="inline-flex h-10 items-center rounded-lg bg-brand px-4 text-[13.5px] font-medium text-white transition hover:bg-brand-hover"
        >
          Or just book a call →
        </a>
      </div>
      <p className="mt-3 text-[12px] leading-[1.5] text-muted">
        Free — use it, share it, keep it. When the report finds real hours, we&apos;ll help you
        get them back.
      </p>
    </div>
  );
}

function StepItem({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3 text-[14px] leading-[1.55] text-dim">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-raised font-display text-[12.5px] font-bold text-ink">
        {n}
      </span>
      <span className="pt-0.5">{children}</span>
    </li>
  );
}

function SnapshotReport({
  report,
  contact,
}: {
  report: Report;
  contact: { name: string; email: string; business: string };
}) {
  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  return (
    <div>
      <style>{`@media print {
        body * { visibility: hidden; }
        #snapshot-report, #snapshot-report * { visibility: visible; }
        #snapshot-report { position: absolute; inset: 0; margin: 0; border: none; box-shadow: none; }
      }`}</style>

      <div
        id="snapshot-report"
        className="rounded-[14px] border border-border bg-background p-7 shadow-[var(--shadow-card)] sm:p-9"
      >
        <h3 className="font-display text-[28px] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Where {contact.business || contact.name} is leaving hours on the table
        </h3>
        <p className="mt-1.5 text-[12.5px] text-muted">
          Prepared for {contact.name} · {today} · {report.business_type}
        </p>

        <div className="mt-7 flex items-center gap-5">
          <div className="font-display text-[52px] font-bold leading-none text-brand">
            {report.score}
            <span className="text-[18px] text-muted">/100</span>
          </div>
          <div className="flex-1">
            <div className="h-2.5 overflow-hidden rounded-full bg-raised">
              <div className="h-full bg-brand" style={{ width: `${report.score}%` }} />
            </div>
            <p className="mt-2 text-[13px] leading-[1.5] text-dim">
              Your AI-readiness score. Everything below ladders to the goal you gave us:{" "}
              <span className="text-ink">&ldquo;{report.goal}&rdquo;</span>
            </p>
          </div>
        </div>

        <h4 className="mt-9 font-display text-[17px] font-bold text-ink">
          Three places your hours are going
        </h4>
        <div className="mt-3 space-y-3">
          {report.findings.map((f, i) => (
            <div key={i} className="rounded-[12px] border border-border bg-surface p-5">
              <div className="flex items-baseline gap-3">
                <span className="font-display text-[15px] font-bold text-brand">0{i + 1}</span>
                <span className="font-display text-[15.5px] font-bold text-ink">{f.title}</span>
                <span className="ml-auto shrink-0 text-[12.5px] font-medium text-brand">
                  {f.hours}
                </span>
              </div>
              <p className="mt-2 text-[14px] leading-[1.55] text-dim">{f.before}</p>
              <p className="mt-1 text-[14px] leading-[1.55] text-ink">→ {f.after}</p>
            </div>
          ))}
        </div>

        <h4 className="mt-9 font-display text-[17px] font-bold text-ink">
          Start here: one tool, this week
        </h4>
        <div className="mt-3 flex flex-wrap items-center gap-x-8 gap-y-3 rounded-[12px] border border-border bg-surface p-5">
          <div className="min-w-[220px] flex-1">
            <div className="font-display text-[16px] font-bold text-ink">{report.tool.name}</div>
            <p className="mt-1 text-[13.5px] leading-[1.5] text-dim">{report.tool.why}</p>
          </div>
          <Stat label="Cost" value={report.tool.cost} />
          <Stat label="Setup" value={report.tool.setup} />
        </div>

        <div className="mt-9 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-[12px] border border-border bg-surface p-6 text-center">
            <div className="font-display text-[34px] font-bold text-brand">
              {report.hours_week} hrs
            </div>
            <p className="mt-1 text-[13px] text-dim">
              reclaimable every week — from your own numbers
            </p>
          </div>
          <div className="rounded-[12px] border border-border bg-surface p-6 text-center">
            <div className="font-display text-[34px] font-bold text-brand">
              ${report.value_month.toLocaleString()}
            </div>
            <p className="mt-1 text-[13px] text-dim">
              per month, at the hourly value you gave us
            </p>
          </div>
        </div>

        <p className="mt-7 text-[12.5px] leading-[1.6] text-muted">
          This snapshot was built from a 3-minute conversation. The full assessment goes nine
          sections deep: an impact–effort matrix, six quick wins, a full tool stack with ROI
          math, and a 4-day rollout plan.
        </p>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3 print:hidden">
        <a
          href={BOOK_CALL_URL}
          className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover"
        >
          Book the full assessment →
        </a>
        <button
          onClick={() => window.print()}
          className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
        >
          Download as PDF
        </button>
        <p className="w-full text-[12.5px] text-muted sm:w-auto">
          If the full assessment doesn&apos;t find you $999/month in recoverable time, you
          don&apos;t pay.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted">
        {label}
      </div>
      <div className="mt-0.5 text-[14px] font-medium text-ink">{value}</div>
    </div>
  );
}
