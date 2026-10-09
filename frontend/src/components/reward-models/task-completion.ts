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
  return point && task ? { ...point, objective: task.objective } : null;
}

export function completionPath(tasks: TaskCompletion[], count: number): string {
  const x = (index: number) => (index + 0.5) / count * 1000;
  const y = (value: number) => 100 - value * 100;
  const paths: string[] = [];
  for (const task of tasks) {
    let path = "";
    for (const [i, point] of task.checkpoints.entries()) {
      if (point.completion === null) { path = ""; continue; }
      // A plateau means the last supported estimate, not inferred progress
      // between checkpoints. Unknown evidence and new requests break the line.
      const next = task.checkpoints[i + 1];
      path = `${path ? `V${y(point.completion)}` : `M${x(point.index)},${y(point.completion)}`}H${x(next?.index ?? task.last)}`;
      paths.push(path);
    }
  }
  return paths.join(" ");
}
