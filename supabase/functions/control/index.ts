import { createClient } from "npm:@supabase/supabase-js@2.45.4";
const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const ACTIONS = new Set(["pause_entries", "resume_entries", "engage_kill_switch", "run_paper_session"]);
const MAX_BODY_BYTES = 4096;
function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const permitted = ALLOWED_ORIGINS.has(origin) || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return permitted ? { "access-control-allow-origin": origin, "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info", "access-control-max-age": "86400", "vary": "Origin" } : {};
}
function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...cors(req) } });
}
async function authorize(req: Request): Promise<{ userId: string } | Response> {
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(req, 401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL")!, anon = Deno.env.get("SUPABASE_ANON_KEY")!, serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const userClient = createClient(url, anon, { global: { headers: { Authorization: auth } } });
  const { data, error } = await userClient.auth.getUser();
  if (error || !data.user) return reply(req, 401, { error: "invalid or expired session" });
  const admin = createClient(url, serviceKey, { auth: { persistSession: false } });
  const { data: allowed, error: allowError } = await admin.from("operator_allowlist").select("user_id").eq("user_id", data.user.id).maybeSingle();
  if (allowError) return reply(req, 503, { error: "operator authorization lookup failed" });
  if (!allowed) return reply(req, 403, { error: "not an authorized operator" });
  return { userId: data.user.id };
}
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { status: 200, headers: cors(req) });
  if (req.method !== "POST") return reply(req, 405, { error: "method not allowed" });
  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return reply(req, 413, { error: "request too large" });
  let body: Record<string, unknown>;
  try { body = JSON.parse(raw); if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error(); }
  catch { return reply(req, 400, { error: "invalid JSON" }); }
  if (Object.keys(body).some((key) => !["action", "idempotency_key", "reason"].includes(key))) return reply(req, 400, { error: "unexpected field" });
  const action = body.action, key = body.idempotency_key, reason = body.reason;
  if (typeof action !== "string" || !ACTIONS.has(action)) return reply(req, 400, { error: "action is not permitted" });
  if (typeof key !== "string" || key.length < 8 || key.length > 128) return reply(req, 400, { error: "idempotency_key must be 8-128 characters" });
  if (reason !== undefined && (typeof reason !== "string" || reason.length > 300)) return reply(req, 400, { error: "reason must be at most 300 characters" });
  const who = await authorize(req);
  if (who instanceof Response) return who;
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
  const { data, error } = await admin.from("operator_commands").insert({ action, requested_by: who.userId, idempotency_key: key, reason: reason ?? null })
    .select("id,status,requested_at").single();
  if (error) {
    if (error.code === "23505") {
      const { data: prior } = await admin.from("operator_commands").select("id,status,requested_at,action").eq("idempotency_key", key).single();
      return reply(req, 200, { duplicate: true, command: prior });
    }
    return reply(req, 500, { error: "command could not be queued" });
  }
  return reply(req, 202, { command: data });
});