export function stashSlugFromInput(input: string): string {
  const value = input.trim();
  if (!value) return "";

  const pathMatch = value.match(/(?:^|\/)cartridges\/([^/?#]+)/i);
  if (pathMatch?.[1]) return pathMatch[1];

  if (/^[A-Za-z0-9][A-Za-z0-9-]*$/.test(value)) return value;

  return "";
}
