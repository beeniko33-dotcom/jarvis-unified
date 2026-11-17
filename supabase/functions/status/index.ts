import { createClient } from "npm:@supabase/supabase-js@2.45.4";
import postgres from "npm:postgres@3.4.7";
const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const permitted = ALLOWED_ORIGINS.has(origin) || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return permitted ? { "access-control-allow-origin": origin, "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info", "access-control-max-age": "86400", "vary": "Origin" } : {};
}
function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...cors(req) } });
}
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { status: 200, headers: cors(req) });
  if (req.method !== "GET") return reply(req, 405, { error: "method not allowed" });
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(req, 401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL"), anon = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"), dbUrl = Deno.env.get("SUPABASE_DB_URL");
  if (!url || !anon || !serviceKey || !dbUrl) return reply(req, 503, { error: "status service configuration incomplete" });
  const userClient = createClient(url, anon, { global: { headers: { Authorization: auth } } });
  const { data: userData, error: userError } = await userClient.auth.getUser();
  if (userError || !userData.user) return reply(req, 401, { error: "invalid or expired session" });
  const admin = createClient(url, serviceKey, { auth: { persistSession: false } });
  const { data: allowed, error: allowError } = await admin.from("operator_allowlist")
    .select("user_id").eq("user_id", userData.user.id).maybeSingle();
  if (allowError) return reply(req, 503, { error: "operator authorization lookup failed" });
  if (!allowed) return reply(req, 403, { error: "not an authorized operator" });
  const sql = postgres(dbUrl, { max: 1, prepare: false, connect_timeout: 8, idle_timeout: 5 });
  try {
    // The installed local control worker writes public.operator_status, not worker_heartbeats.
    const [workerResult, commandResult, observationResult, auditResult] = await Promise.all([
      admin.from("operator_status").select("worker_id,reported_at,health,mode,kill_switch_engaged,entries_paused,last_paper_session_date,details,updated_at")
        .order("reported_at", { ascending: false }).limit(10),
      admin.from("operator_commands").select("id,action,status,requested_at,completed_at,reason,result")
        .order("requested_at", { ascending: false }).limit(25),
      sql`select count(*)::int as count, max(received_at) as latest from jarvis_private.market_observations`,
      sql`select count(*)::int as count, max(recorded_at) as latest from jarvis_private.runtime_audit_events`,
    ]);
    if (workerResult.error) return reply(req, 503, { error: "worker status lookup failed" });
    if (commandResult.error) return reply(req, 503, { error: "command history lookup failed" });
    const workers = (workerResult.data ?? []).map((w) => ({
      ...w, worker_type: (w.details && typeof w.details.worker_type === "string") ? w.details.worker_type : "local-control-worker", software_version: (w.details && typeof w.details.software_version === "string") ? w.details.software_version : null, git_commit: (w.details && typeof w.details.git_commit === "string") ? w.details.git_commit : null,
      kill_switch_engaged: w.kill_switch_engaged, entries_paused: w.entries_paused,
    }));
    return reply(req, 200, {
      generated_at: new Date().toISOString(), mode: "paper", live_trading: "disabled_by_design",
      workers, recent_commands: commandResult.data ?? [],
      telemetry: { market_observations: observationResult[0]?.count ?? 0,
        latest_market_observation_at: observationResult[0]?.latest ?? null,
        runtime_audit_events: auditResult[0]?.count ?? 0, latest_runtime_event_at: auditResult[0]?.latest ?? null },
    });
  } catch (_error) {
    return reply(req, 503, { error: "worker status database query failed" });
  } finally { await sql.end({ timeout: 2 }); }
});