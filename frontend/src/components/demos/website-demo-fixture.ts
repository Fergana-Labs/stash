import type { WebsiteDemoData } from "./website-demo-data";

export const demoFixture: WebsiteDemoData = {
  version: 1,
  model_id: "eval-1",
  session_id: "session-1",
  title: "Gather",
  file: "index.html",
  brief: "A clear landing page",
  reference_count: 2,
  held_out_n: 4,
  agreement: 0.75,
  model_version: 1,
  selected_iteration: 1,
  recorded: true,
  artifacts: [0.2, 0.91, 0.5].map((score, iteration) => ({
    iteration,
    score,
    name: `v${iteration}`,
    html: "<html><script>window.executed = true</script></html>",
    image: "data:image/png;base64,aA==",
    description: "Recorded pixels",
    prediction_id: `prediction-${iteration}`,
    label: score > 0.5 ? "liked" : "disliked",
    accepted: iteration === 1,
    rubric: {},
  })),
  references: [
    {
      image: "data:image/png;base64,aA==",
      label: "liked",
      note: "Clear",
      split: "eval",
    },
  ],
  criteria: [{ id: "clear", prompt: "Is the hierarchy clear?" }],
  transcript: [{ role: "user", text: "Prefer clear hierarchy" }],
};
