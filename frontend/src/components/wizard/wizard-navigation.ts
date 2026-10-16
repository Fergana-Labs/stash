export interface PendingWizardMessage { id: number; text: string; kind: "message" | "event" }

const key = (sessionId: string) => `stash-wizard-pending:${sessionId}`;

/** Carry a workspace action into the full-page wizard without putting its text in the URL. */
export function stageWizardMessage(sessionId: string, message: PendingWizardMessage) {
  sessionStorage.setItem(key(sessionId), JSON.stringify(message));
}

/** Consume once so returning to or reloading the wizard cannot send the action again. */
export function takeWizardMessage(sessionId: string): PendingWizardMessage | null {
  const stored = sessionStorage.getItem(key(sessionId));
  sessionStorage.removeItem(key(sessionId));
  if (!stored) return null;
  try {
    const value = JSON.parse(stored);
    return typeof value.id === "number" && typeof value.text === "string"
      && (value.kind === "message" || value.kind === "event") ? value : null;
  } catch { return null; }
}
