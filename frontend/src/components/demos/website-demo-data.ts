export interface WebsiteRevision {
  iteration: number;
  name: string;
  html: string;
  image: string;
  description: string;
  score: number;
  prediction_id: string;
  label: string;
  accepted?: boolean;
  rubric: Record<string, Record<string, number>>;
}
export interface WebsiteDemoData {
  version: number;
  model_id: string;
  session_id: string;
  title: string;
  file: string;
  brief: string;
  reference_count: number;
  held_out_n: number;
  agreement: number;
  model_version: number;
  selected_iteration: number;
  artifacts: WebsiteRevision[];
  references: { image: string; label: string; note: string; split: string }[];
  criteria: { id: string; prompt: string }[];
  transcript: (
    | { role: "user"; text: string }
    | { role: "assistant"; parts: { type: "text"; text: string }[] }
  )[];
  recorded: boolean;
}

const image = (v: unknown): v is string =>
  typeof v === "string" && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(v);
const probability = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1;

/** A demo is ordinary owner-scoped trace data, not a globally shared fixture. */
export function websiteDemoData(value: unknown): WebsiteDemoData | null {
  if (!value || typeof value !== "object") return null;
  const d = value as WebsiteDemoData;
  if (
    d.version !== 1 ||
    d.recorded !== true ||
    typeof d.model_id !== "string" ||
    typeof d.session_id !== "string" ||
    typeof d.file !== "string" ||
    typeof d.title !== "string" ||
    typeof d.brief !== "string" ||
    !Number.isInteger(d.reference_count) ||
    d.reference_count < 1 ||
    !Number.isInteger(d.held_out_n) ||
    d.held_out_n < 1 ||
    !Number.isInteger(d.model_version) ||
    d.model_version < 1 ||
    !Array.isArray(d.artifacts) ||
    !d.artifacts.length ||
    !Array.isArray(d.references) ||
    !Array.isArray(d.criteria) ||
    !Array.isArray(d.transcript) ||
    !probability(d.agreement)
  )
    return null;
  if (
    !d.artifacts.every(
      (a) =>
        a &&
        Number.isInteger(a.iteration) &&
        a.iteration >= 0 &&
        image(a.image) &&
        probability(a.score) &&
        typeof a.html === "string" &&
        typeof a.name === "string" &&
        typeof a.description === "string" &&
        typeof a.prediction_id === "string" &&
        a.rubric &&
        typeof a.rubric === "object",
    )
  )
    return null;
  if (
    !d.references.every(
      (r) =>
        r &&
        image(r.image) &&
        ["liked", "disliked"].includes(r.label) &&
        typeof r.note === "string",
    )
  )
    return null;
  if (
    !d.criteria.every(
      (q) => q && typeof q.id === "string" && typeof q.prompt === "string",
    )
  )
    return null;
  if (
    !d.transcript.every(
      (t) =>
        t &&
        (t.role === "user"
          ? typeof t.text === "string"
          : t.role === "assistant" &&
            Array.isArray(t.parts) &&
            t.parts.every(
              (p) => p && p.type === "text" && typeof p.text === "string",
            )),
    )
  )
    return null;
  if (
    new Set(d.artifacts.map((a) => a.iteration)).size !== d.artifacts.length ||
    !d.artifacts.some((a) => a.iteration === 0) ||
    !d.artifacts.some((a) => a.iteration === d.selected_iteration)
  )
    return null;
  return d;
}

/** Include rejected attempts: the selected artifact must be the measured best. */
export function bestWebsiteRevision(artifacts: WebsiteRevision[]) {
  return artifacts.reduce((best, next) =>
    next.score > best.score ? next : best,
  );
}
