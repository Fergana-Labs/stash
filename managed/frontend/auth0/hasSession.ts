export async function hasAuth0Session(): Promise<boolean> {
  try {
    const res = await fetch("/auth/profile", { credentials: "include" });
    return res.ok;
  } catch {
    return false;
  }
}
