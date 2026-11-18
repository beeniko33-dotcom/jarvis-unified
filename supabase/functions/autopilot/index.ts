import { createClient } from "npm:@supabase/supabase-js@2.45.4";
const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const ok = ALLOWED_ORIGINS.has(origin) || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return ok ? { "access-control-allow-origin": origin, "access-control-allow-methods": "POST, GET, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info", "vary": "Origin" } : {};
}
function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...HEADERS, ...cors(req) } });
}
async function operator(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return { response: reply(req, 401, { error: "sign in required" }) };
  const url = Deno.env.get("SUPABASE_URL")!, anon = Deno.env.get("SUPABASE_ANON_KEY")!, key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const user = createClient(url, anon, { global: { headers: { Authorization: auth } } });
  const { data, error } = await user.auth.getUser();
  if (error || !data.user) return { response: reply(req, 401, { error: "invalid or expired session" }) };
  const admin = createClient(url, key, { auth: { persistSession: false } });
  const { data: allowed, error: e } = await admin.from("operator_allowlist").select("user_id").eq("user_id", data.user.id).maybeSingle();
  if (e) return { response: reply(req, 503, { error: "operator authorization lookup failed" }) };
  if (!allowed) return { response: reply(req, 403, { error: "not an authorized operator" }) };
  return { userId: data.user.id, admin };
}
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(req) });
  if (!["POST", "GET"].includes(req.method)) return reply(req, 405, { error: "method not allowed" });
  const who = await operator(req);
  if (who.response) return who.response;
  if (req.method === "GET") {
    const { data, error } = await who.admin.from("jarvis_autopilot_tasks")
      .select("id,requested_at,task_text,status,executor_state,approval_required")
      .eq("requested_by", who.userId).order("requested_at", { ascending: false }).limit(20);
    if (error) return reply(req, 503, { error: "task history unavailable" });
    return reply(req, 200, { tasks: data ?? [], execution_enabled: false });
  }
  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > 6000) return reply(req, 413, { error: "request too large" });
  let body: Record<string, unknown>;
  try { body = JSON.parse(raw); if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error(); }
  catch { return reply(req, 400, { error: "invalid JSON" }); }
  if (Object.keys(body).some(k => k !== "task_text")) return reply(req, 400, { error: "unexpected field" });
  const task = body.task_text;
  if (typeof task !== "string" || task.trim().length < 12 || task.trim().length > 4000)
    return reply(req, 400, { error: "task_text must be 12-4000 characters" });
  const { data, error } = await who.admin.from("jarvis_autopilot_tasks")
    .insert({ requested_by: who.userId, task_text: task.trim() })
    .select("id,requested_at,status,executor_state,approval_required").single();
  if (error) return reply(req, 503, { error: "task proposal could not be saved" });
  return reply(req, 202, { task: data, message: "Saved for operator review. No code or system action has been executed.", execution_enabled: false });
});