// Deduplicates in-flight requests: if multiple callers ask for a token
// simultaneously, only one fetch is made and all callers share the result.
let _inFlight: Promise<string | null> | null = null;

export async function fetchAccessToken(): Promise<string | null> {
  if (_inFlight) return _inFlight;

  _inFlight = fetch("/api/auth/token")
    .then(async (res) => {
      if (!res.ok) return null;
      const data = await res.json();
      return (data.token as string) || null;
    })
    .catch(() => null)
    .finally(() => {
      _inFlight = null;
    });

  return _inFlight;
}
