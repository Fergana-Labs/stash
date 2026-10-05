/** Color intensity tracks distance from the training reference midpoint. */
export function creditColor(credit: number, alpha = 1): string {
  const strength = Math.min(1, Math.abs(credit));
  return `hsla(${credit < 0 ? 0 : 160}, ${15 + strength * 60}%, 43%, ${alpha})`;
}

export function formatCredit(credit: number): string {
  return `${credit >= 0 ? "+" : ""}${credit.toFixed(2)}`;
}
