// Operator control endpoint. Paper-only by construction: the action set is fixed here AND by a
// database check constraint. There is deliberately no live-trading action.
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const ACTIONS = new Set([
  "pause_entries",
  "resume_entries",
  "engage_kill_switch",
  "run_paper_session",
]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const MAX_BODY_BYTES = 4096;

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

async function authorize(req: Request): Promise<{ userId: string } | Response> {
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL")!;
  const anon = Deno.env.get("SUPABASE_ANON_KEY")!;
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

  const userClient = createClient(url, anon, { global: { headers: { Authorization: auth } } });
  const { data, error } = await userClient.auth.getUser();
  if (error || !data.user) return reply(401, { error: "invalid or expired session" });

  const admin = createClient(url, serviceKey, { auth: { persistSession: false } });
  const { data: allowed } = await admin
    .from("operator_allowlist")
    .select("user_id")
    .eq("user_id", data.user.id)
    .maybeSingle();
  if (!allowed) return reply(403, { error: "not an authorized operator" });
  return { userId: data.user.id };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply(405, { error: "method not allowed" });

  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) {
    return reply(413, { error: "request too large" });
  }
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
  } catch {
    return reply(400, { error: "invalid JSON" });
  }

  const allowedKeys = new Set(["action", "idempotency_key", "reason"]);
  if (Object.keys(body).some((key) => !allowedKeys.has(key))) {
    return reply(400, { error: "unexpected field" });
  }
  const action = body.action;
  if (typeof action !== "string" || !ACTIONS.has(action)) {
    return reply(400, { error: "action is not permitted" });
  }
  const key = body.idempotency_key;
  if (typeof key !== "string" || key.length < 8 || key.length > 128) {
    return reply(400, { error: "idempotency_key must be 8-128 characters" });
  }
  const reason = body.reason;
  if (reason !== undefined && (typeof reason !== "string" || reason.length > 300)) {
    return reply(400, { error: "reason must be at most 300 characters" });
  }

  const who = await authorize(req);
  if (who instanceof Response) return who;

  const admin = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );
  const { data, error } = await admin
    .from("operator_commands")
    .insert({
      action,
      requested_by: who.userId,
      idempotency_key: key,
      reason: (reason as string | undefined) ?? null,
    })
    .select("id,status,requested_at")
    .single();

  if (error) {
    // Same key again: return the original command rather than queueing a duplicate.
    if (error.code === "23505") {
      const { data: prior } = await admin
        .from("operator_commands")
        .select("id,status,requested_at,action")
        .eq("idempotency_key", key)
        .single();
      return reply(200, { duplicate: true, command: prior });
    }
    return reply(500, { error: "command could not be queued" });
  }
  return reply(202, { command: data });
});
