import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import postgres from "npm:postgres@3.4.7";

const DB_URL = Deno.env.get("SUPABASE_DB_URL");
const SECRET_KEYS = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
const SECRET_API_KEY = SECRET_KEYS.default ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

function tokenMatches(supplied: string, expected: string): boolean {
  const a = new TextEncoder().encode(supplied);
  const b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
}

function stable(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return "{" + Object.keys(obj).sort().map((k) => JSON.stringify(k) + ":" + stable(obj[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function scrub(value: unknown, depth = 0): unknown {
  if (depth > 5) throw new Error("payload nesting exceeds limit");
  if (Array.isArray(value)) {
    if (value.length > 100) throw new Error("payload array too large");
    return value.map((v) => scrub(v, depth + 1));
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      if (/(token|secret|password|authorization|api.?key|private.?key|mnemonic|seed.?phrase|credential)/i.test(key)) {
        throw new Error("sensitive fields are not accepted in audit payloads");
      }
      out[key] = scrub(val, depth + 1);
    }
    return out;
  }
  if (typeof value === "string" && value.length > 4000) throw new Error("payload string too long");
  return value;
}

function requiredString(obj: Record<string, unknown>, key: string, max: number): string {
  const v = obj[key];
  if (typeof v !== "string" || !v.trim() || v.length > max) {
    throw new Error(key + " is required and must be at most " + max + " characters");
  }
  return v.trim();
}

const sql = DB_URL ? postgres(DB_URL, { max: 1, prepare: false, connect_timeout: 10, idle_timeout: 20 }) : null;

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  // Supabase secret API keys are opaque: callers send them in apikey only.
  // JWT verification is disabled for this service-to-service function; this
  // constant-time comparison is the mandatory authentication gate.
  const suppliedApiKey = req.headers.get("apikey") ?? "";
  if (!SECRET_API_KEY || !tokenMatches(suppliedApiKey, SECRET_API_KEY)) {
    return json({ error: "secret_api_key_required" }, 403);
  }
  if (!sql) return json({ error: "database_connection_not_configured" }, 500);

  let body: Record<string, unknown>;
  try {
    body = await req.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("JSON object required");
  } catch (e) {
    return json({ error: "invalid_json", detail: e instanceof Error ? e.message : "invalid body" }, 400);
  }

  try {
    const kind = requiredString(body, "kind", 32);

    if (kind === "heartbeat") {
      const worker_id = requiredString(body, "worker_id", 128);
      const worker_type = requiredString(body, "worker_type", 64);
      const software_version = requiredString(body, "software_version", 128);
      const health = requiredString(body, "health", 16);
      if (!["healthy", "degraded", "stopped", "blocked"].includes(health)) throw new Error("invalid health");
      const git_commit = typeof body.git_commit === "string" ? body.git_commit.slice(0, 64) : null;
      const started_at = typeof body.started_at === "string" ? body.started_at : null;
      const details = scrub(body.details ?? {}) as Record<string, unknown>;
      await sql`
        insert into jarvis_private.worker_heartbeats
          (worker_id, worker_type, reported_at, started_at, software_version, git_commit, mode, health, details, updated_at)
        values
          (${worker_id}, ${worker_type}, now(), ${started_at}, ${software_version}, ${git_commit}, 'paper', ${health}, ${sql.json(details)}, now())
        on conflict (worker_id) do update set
          worker_type = excluded.worker_type, reported_at = excluded.reported_at,
          started_at = coalesce(excluded.started_at, jarvis_private.worker_heartbeats.started_at),
          software_version = excluded.software_version, git_commit = excluded.git_commit,
          mode = 'paper', health = excluded.health, details = excluded.details, updated_at = now()
      `;
      return json({ ok: true, kind, mode: "paper", worker_id, health, recorded: true });
    }

    if (kind === "market_observation") {
      const source_id = requiredString(body, "source_id", 128);
      const symbol = requiredString(body, "symbol", 64);
      const timeframe = requiredString(body, "timeframe", 32);
      const event_time = requiredString(body, "event_time", 64);
      const parsedTime = Date.parse(event_time);
      if (!Number.isFinite(parsedTime)) throw new Error("event_time must be an ISO timestamp");
      if (parsedTime > Date.now() + 60_000) throw new Error("future-dated market observations are rejected");
      const values_json = body.values_json;
      if (!values_json || typeof values_json !== "object" || Array.isArray(values_json)) throw new Error("values_json object required");
      const canonical = stable({ source_id, symbol, timeframe, event_time: new Date(parsedTime).toISOString(), values_json });
      const content_hash = await sha256(canonical);
      const rows = await sql`
        insert into jarvis_private.market_observations
          (source_id, event_time, received_at, symbol, timeframe, schema_version, content_hash, values_json, provenance)
        values
          (${source_id}, ${new Date(parsedTime).toISOString()}, now(), ${symbol}, ${timeframe}, 1, ${content_hash}, ${sql.json(values_json)}, 'candidate_unverified')
        on conflict (source_id, content_hash) do nothing
        returning id
      `;
      return json({ ok: true, kind, inserted: rows.length === 1, duplicate: rows.length === 0, content_hash, provenance: "candidate_unverified" });
    }

    if (kind === "audit_event") {
      const event_type = requiredString(body, "event_type", 128);
      const component = requiredString(body, "component", 128);
      const occurred_at = typeof body.occurred_at === "string" ? body.occurred_at : new Date().toISOString();
      if (!Number.isFinite(Date.parse(occurred_at))) throw new Error("occurred_at must be an ISO timestamp");
      const correlation_id = typeof body.correlation_id === "string" ? body.correlation_id.slice(0, 128) : null;
      const payload = scrub(body.payload ?? {}) as Record<string, unknown>;
      const payload_sha256 = await sha256(stable(payload));
      const rows = await sql`
        insert into jarvis_private.runtime_audit_events
          (event_type, occurred_at, correlation_id, component, payload, payload_sha256)
        values
          (${event_type}, ${new Date(Date.parse(occurred_at)).toISOString()}, ${correlation_id}, ${component}, ${sql.json(payload)}, ${payload_sha256})
        returning id
      `;
      return json({ ok: true, kind, event_id: rows[0].id, payload_sha256, recorded: true });
    }

    return json({ error: "unsupported_kind", allowed: ["heartbeat", "market_observation", "audit_event"] }, 400);
  } catch (e) {
    return json({ error: "ingest_failed", detail: e instanceof Error ? e.message : "request failed" }, 400);
  }
});