/**
 * The people this product has as customers. A real app would read the signed-in
 * traveller from its own users table; the demo ships with two so you can switch
 * between them and see that each one's agent knows only their own trips.
 *
 * `id` is what Stash sees as the tenant id — the isolation boundary.
 */
export const TRAVELLERS = [
  { id: "sam", name: "Sam Ellery", email: "sam.ellery@gmail.com" },
  { id: "priya", name: "Priya Raman", email: "priya.raman@gmail.com" },
];

export function travellerById(id: string) {
  const traveller = TRAVELLERS.find((t) => t.id === id);
  if (!traveller) throw new Error(`unknown traveller: ${id}`);
  return traveller;
}
