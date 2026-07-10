import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

import type { LogoutToken, SessionData, SessionDataStore } from "@auth0/nextjs-auth0/types";
import { Pool } from "pg";

// Session policy (SOC 2 idle-timeout control): a session dies after 7 idle
// days, and 30 days after login no matter how active it is. client.ts passes
// the same values to the Auth0 SDK so the session-ID cookie expires in step
// with the row.
export const SESSION_INACTIVITY_SECONDS = 60 * 60 * 24 * 7;
export const SESSION_ABSOLUTE_SECONDS = 60 * 60 * 24 * 30;

export function sessionExpiresAt(createdAtEpochSeconds: number, nowMs: number): Date {
  const idleDeadline = nowMs + SESSION_INACTIVITY_SECONDS * 1000;
  const absoluteDeadline = (createdAtEpochSeconds + SESSION_ABSOLUTE_SECONDS) * 1000;
  return new Date(Math.min(idleDeadline, absoluteDeadline));
}

// Sessions hold Auth0 access/refresh tokens, which — like integration OAuth
// tokens (INTEGRATIONS_ENCRYPTION_KEY) — must be encrypted at rest, not stored
// as readable JSON in the database.
export function encryptSessionData(session: SessionData, secret: string): string {
  const key = createHash("sha256").update(secret).digest();
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(session), "utf8"), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ciphertext]).toString("base64");
}

export function decryptSessionData(encrypted: string, secret: string): SessionData | null {
  const key = createHash("sha256").update(secret).digest();
  const raw = Buffer.from(encrypted, "base64");
  const iv = raw.subarray(0, 12);
  const authTag = raw.subarray(12, 28);
  const ciphertext = raw.subarray(28);
  try {
    const decipher = createDecipheriv("aes-256-gcm", key, iv);
    decipher.setAuthTag(authTag);
    const json = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
    return JSON.parse(json) as SessionData;
  } catch {
    // A row that no longer decrypts (AUTH0_SECRET rotated) is not a session;
    // the user signs in again. Same semantics as the SDK's handling of
    // undecryptable cookies.
    return null;
  }
}

/**
 * Server-side session store backed by the auth0_sessions table (managed
 * migration m0002). The browser cookie holds only an encrypted session ID;
 * deleting the row here kills the session everywhere, instantly.
 */
export class PostgresSessionStore implements SessionDataStore {
  private pool: Pool;
  private secret: string;

  constructor(options: { databaseUrl: string; databaseSsl: boolean; secret: string }) {
    this.pool = new Pool({
      connectionString: options.databaseUrl,
      ssl: options.databaseSsl ? { rejectUnauthorized: false } : undefined,
    });
    this.secret = options.secret;
  }

  async get(id: string): Promise<SessionData | null> {
    const { rows } = await this.pool.query(
      "SELECT data FROM auth0_sessions WHERE id = $1 AND expires_at > now()",
      [id],
    );
    if (rows.length === 0) return null;
    return decryptSessionData(rows[0].data, this.secret);
  }

  async set(id: string, session: SessionData): Promise<void> {
    await this.pool.query(
      `INSERT INTO auth0_sessions (id, data, sub, sid, expires_at)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (id) DO UPDATE
       SET data = EXCLUDED.data, sub = EXCLUDED.sub, sid = EXCLUDED.sid,
           expires_at = EXCLUDED.expires_at, updated_at = now()`,
      [
        id,
        encryptSessionData(session, this.secret),
        session.user.sub,
        session.internal.sid,
        sessionExpiresAt(session.internal.createdAt, Date.now()),
      ],
    );
  }

  // Atomic check-and-write. The SDK rolls sessions through this so that a
  // response racing a logout updates zero rows instead of re-creating the
  // session the logout just deleted — the cookie-resurrection bug that made
  // sign-out a no-op under stateless sessions.
  async update(id: string, session: SessionData): Promise<boolean> {
    const result = await this.pool.query(
      `UPDATE auth0_sessions
       SET data = $2, expires_at = $3, updated_at = now()
       WHERE id = $1`,
      [
        id,
        encryptSessionData(session, this.secret),
        sessionExpiresAt(session.internal.createdAt, Date.now()),
      ],
    );
    return (result.rowCount ?? 0) > 0;
  }

  async delete(id: string): Promise<void> {
    await this.pool.query("DELETE FROM auth0_sessions WHERE id = $1", [id]);
  }

  // Auth0 back-channel logout: revoke by Auth0 session ID when present,
  // otherwise every session of the user.
  async deleteByLogoutToken(token: LogoutToken): Promise<void> {
    if (token.sid) {
      await this.pool.query("DELETE FROM auth0_sessions WHERE sid = $1", [token.sid]);
      return;
    }
    if (token.sub) {
      await this.pool.query("DELETE FROM auth0_sessions WHERE sub = $1", [token.sub]);
    }
  }
}
