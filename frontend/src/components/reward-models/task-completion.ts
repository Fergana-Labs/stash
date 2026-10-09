import type { RmTaskCompletion } from "@/lib/api";

export interface TaskCompletion {
  first: number;
  last: number;
  objective: string;
  checkpoints: { index: number; completion: number | null; reason: string }[];
}

export function taskCompletion(tasks: RmTaskCompletion[], numberById: Map<string, number>): TaskCompletion[] {
  return tasks.flatMap((task) => {
    const first = numberById.get(task.first_step_id);
    const last = numberById.get(task.last_step_id);
    if (first === undefined || last === undefined) return [];
    // Tool outputs share a displayed row with their call. The last evidence in
    // that row wins, rather than moving an output checkpoint to another step.
    const points = new Map<number, TaskCompletion["checkpoints"][number]>();
    for (const point of task.checkpoints) {
      const number = numberById.get(point.step_id);
      if (number === undefined || number < first || number > last) continue;
      const completion = point.completion !== null && Number.isFinite(point.completion)
        && point.completion >= 0 && point.completion <= 1 ? point.completion : null;
      points.set(number, { index: number - 1, completion, reason: point.reason });
    }
    return [{ first: first - 1, last: last - 1, objective: task.objective, checkpoints: [...points.values()].sort((a, b) => a.index - b.index) }];
  });
}

export function completionAt(tasks: TaskCompletion[], index: number) {
  const task = tasks.find((task) => index >= task.first && index <= task.last);
  const point = task?.checkpoints.findLast((point) => point.index <= index);
  if (!point || !task) return null;
  const next = task.checkpoints.find((point) => point.index > index);
  if (point.completion === null || !next || next.completion === null || index === point.index) return { ...point, objective: task.objective };
  const t = (index - point.index) / (next.index - point.index);
  const slopes = checkpointSlopes(task);
  const i = task.checkpoints.indexOf(point);
  const width = next.index - point.index;
  const a = point.completion + slopes[i] * width / 3;
  const b = next.completion - slopes[i + 1] * width / 3;
  return { ...point, objective: task.objective,
    completion: (1 - t) ** 3 * point.completion + 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t ** 2 * b + t ** 3 * next.completion,
    reason: `Between progress estimates at steps ${point.index + 1} and ${next.index + 1}.`,
  };
}

/** Shape-preserving Hermite slopes: follow the data, flatten only at a turn or plateau. */
function checkpointSlopes(task: TaskCompletion): number[] {
  return task.checkpoints.map((point, index, points) => {
    if (point.completion === null) return 0;
    const previous = points[index - 1];
    const next = points[index + 1];
    const left = previous?.completion != null ? (point.completion - previous.completion) / (point.index - previous.index) : null;
    const right = next?.completion != null ? (next.completion - point.completion) / (next.index - point.index) : null;
    if (left === null) return right ?? 0;
    if (right === null) return point.index === task.last ? left : 0;
    if (left * right <= 0) return 0;
    const before = point.index - previous.index;
    const after = next.index - point.index;
    const w1 = 2 * after + before;
    const w2 = after + 2 * before;
    return (w1 + w2) / (w1 / left + w2 / right);
  });
}

export function completionPath(tasks: TaskCompletion[], count: number): string {
  const x = (index: number) => (index + 0.5) / count * 1000;
  const y = (value: number) => 100 - value * 100;
  const paths: string[] = [];
  for (const task of tasks) {
    const slopes = checkpointSlopes(task);
    let connected = false;
    for (const [i, point] of task.checkpoints.entries()) {
      if (point.completion === null) { connected = false; continue; }
      if (!connected) paths.push(`M${x(point.index)},${y(point.completion)}`);
      const next = task.checkpoints[i + 1];
      if (next?.completion != null) {
        // Shared slopes make the curve C1 continuous without an artificial
        // ease-in/ease-out at each checkpoint. No overshoot or invented wiggles.
        const third = (x(next.index) - x(point.index)) / 3;
        const width = next.index - point.index;
        paths.push(`C${x(point.index) + third},${y(point.completion + slopes[i] * width / 3)} ${x(next.index) - third},${y(next.completion - slopes[i + 1] * width / 3)} ${x(next.index)},${y(next.completion)}`);
      } else paths.push(`H${x(next?.index ?? task.last)}`);
      connected = true;
    }
  }
  return paths.join(" ");
}
