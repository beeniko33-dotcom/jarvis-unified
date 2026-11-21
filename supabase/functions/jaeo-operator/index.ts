import { createClient, type SupabaseClient, type User } from "npm:@supabase/supabase-js@2.45.4";

const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const TASK_ROLES = new Set(["orchestrator","engineering","database","infrastructure","security","qa","research","release","audit"]);
const APPROVAL_ACTIONS = new Set(["change_code","change_schema","change_secret","provision_resource","create_cron","deploy_preview","merge_pull_request"]);
const PRODUCTION_IDS = new Set(["zythldptlplyutphgxpg","db.zythldptlplyutphgxpg.supabase.co","jarvis-control-worker","production","prod"]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_BODY = 12_000;

function response(status: number, body: unknown, origin?: string) {
  const headers: Record<string,string> = { ...JSON_HEADERS };
  if (origin) {
    headers["access-control-allow-origin"] = origin;
    headers["access-control-allow-methods"] = "POST, OPTIONS";
    headers["access-control-allow-headers"] = "authorization, apikey, content-type, x-client-info";
    headers["access-control-max-age"] = "600";
    headers["vary"] = "Origin";
  }
  return new Response(JSON.stringify(body), { status, headers });
}
function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  const obj = value as Record<string,unknown>;
  return "{" + Object.keys(obj).sort().map((key) => JSON.stringify(key) + ":" + canonical(obj[key])).join(",") + "}";
}
async function sha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2,"0")).join("");
}
function isRecord(value: unknown): value is Record<string,unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function isProductionResource(resource: string) {
  const normalized = resource.trim().toLowerCase();
  return PRODUCTION_IDS.has(normalized) || normalized.startsWith("prod:") || normalized.includes("zythldptlplyutphgxpg");
}
function operator(user: User) {
  return user.app_metadata?.jaeo_operator === true;
}

Deno.serve(async (req: Request) => {
  const allowedOrigins = new Set((Deno.env.get("JAEO_ALLOWED_ORIGINS") ?? "").split(",").map((v) => v.trim()).filter(Boolean));
  const origin = req.headers.get("origin") ?? "";
  const corsOrigin = allowedOrigins.has(origin) ? origin : undefined;
  if (req.method === "OPTIONS") return corsOrigin
    ? new Response("ok", { status: 204, headers: { "access-control-allow-origin": origin, "access-control-allow-methods": "POST, OPTIONS", "access-control-allow-headers": "authorization, apikey, content-type, x-client-info", "access-control-max-age": "600", "vary": "Origin" } })
    : response(403, { error: "origin not allowed" });
  if (req.method !== "POST") return response(405, { error: "method not allowed" }, corsOrigin);

  const authorization = req.headers.get("authorization") ?? "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!token) return response(401, { error: "authentication required" }, corsOrigin);

  const url = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anonKey || !serviceKey) return response(503, { error: "JAEO service is not configured" }, corsOrigin);

  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY) return response(413, { error: "request too large" }, corsOrigin);
  let body: Record<string,unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) throw new Error("object required");
    body = parsed;
  } catch {
    return response(400, { error: "invalid JSON object" }, corsOrigin);
  }

  const userClient = createClient(url, anonKey, { global: { headers: { Authorization: authorization } }, auth: { persistSession: false, autoRefreshToken: false } });
  const { data: authData, error: authError } = await userClient.auth.getUser(token);
  if (authError || !authData.user) return response(401, { error: "invalid or expired session" }, corsOrigin);
  const user = authData.user;
  const admin: SupabaseClient = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

  try {
    switch (body.operation) {
      case "create_task": {
        const allowed = ["operation","idempotency_key","title","description","agent_role","workspace_scope"];
        if (Object.keys(body).some((key) => !allowed.includes(key))) return response(400, { error: "unexpected field" }, corsOrigin);
        if (typeof body.idempotency_key !== "string" || body.idempotency_key.length < 8 || body.idempotency_key.length > 128
          || typeof body.title !== "string" || body.title.trim().length < 1 || body.title.length > 200
          || typeof body.description !== "string" || body.description.length > 4000
          || typeof body.agent_role !== "string" || !TASK_ROLES.has(body.agent_role)
          || !["all","core"].includes(String(body.workspace_scope ?? "all"))) {
          return response(400, { error: "invalid task fields" }, corsOrigin);
        }
        const { data, error } = await admin.schema("jarvis_private").from("jaeo_tasks").insert({
          idempotency_key: body.idempotency_key, title: body.title.trim(), description: body.description,
          agent_role: body.agent_role, workspace_scope: body.workspace_scope ?? "all",
          autonomy: "supervised", feedback_mode: "both", mode: "supervised", live_trading_enabled: false,
          requested_by: user.id,
        }).select("id,idempotency_key,title,description,agent_role,workspace_scope,autonomy,feedback_mode,mode,status,created_at").single();
        if (error?.code === "23505") {
          const { data: existing, error: lookupError } = await admin.schema("jarvis_private").from("jaeo_tasks")
            .select("id,idempotency_key,title,description,agent_role,workspace_scope,autonomy,feedback_mode,mode,status,created_at,requested_by")
            .eq("idempotency_key", body.idempotency_key).maybeSingle();
          if (lookupError || !existing || existing.requested_by !== user.id) return response(409, { error: "idempotency key conflict" }, corsOrigin);
          return response(200, { task: existing, duplicate: true }, corsOrigin);
        }
        if (error || !data) return response(500, { error: "task could not be created" }, corsOrigin);
        return response(201, { task: data, duplicate: false }, corsOrigin);
      }
      case "list_tasks": {
        if (Object.keys(body).some((key) => key !== "operation")) return response(400, { error: "unexpected field" }, corsOrigin);
        let query = admin.schema("jarvis_private").from("jaeo_tasks")
          .select("id,title,description,agent_role,workspace_scope,autonomy,feedback_mode,mode,status,created_at,started_at,completed_at,result,requested_by")
          .order("created_at", { ascending: false }).limit(50);
        if (!operator(user)) query = query.eq("requested_by", user.id);
        const { data, error } = await query;
        if (error) return response(500, { error: "tasks could not be loaded" }, corsOrigin);
        return response(200, { tasks: data ?? [] }, corsOrigin);
      }
      case "request_approval": {
        const allowed = ["operation","task_id","action","resource_id","request"];
        if (Object.keys(body).some((key) => !allowed.includes(key))) return response(400, { error: "unexpected field" }, corsOrigin);
        if (typeof body.task_id !== "string" || !UUID.test(body.task_id)
          || typeof body.action !== "string" || !APPROVAL_ACTIONS.has(body.action)
          || typeof body.resource_id !== "string" || body.resource_id.trim().length < 1 || body.resource_id.length > 256
          || !isRecord(body.request) || new TextEncoder().encode(canonical(body.request)).byteLength > 8192) {
          return response(400, { error: "invalid approval request" }, corsOrigin);
        }
        if (isProductionResource(body.resource_id)) return response(403, { error: "production resources are permanently outside JAEO authority" }, corsOrigin);
        const { data: task, error: taskError } = await admin.schema("jarvis_private").from("jaeo_tasks")
          .select("id,requested_by").eq("id", body.task_id).maybeSingle();
        if (taskError || !task || task.requested_by !== user.id) return response(404, { error: "task not found" }, corsOrigin);
        const requestHash = await sha256({ action: body.action, resource_id: body.resource_id, request: body.request });
        const { data, error } = await admin.schema("jarvis_private").from("jaeo_approvals").insert({
          task_id: body.task_id, action: body.action, resource_id: body.resource_id.trim(),
          request: body.request, status: "pending", requested_by: user.id, request_hash: requestHash,
        }).select("id,task_id,action,resource_id,status,requested_at,expires_at,request_hash").single();
        if (error || !data) return response(500, { error: "approval request could not be recorded" }, corsOrigin);
        return response(201, { approval: data, note: "Approval records authorization only; this API never executes the requested action." }, corsOrigin);
      }
      case "decide_approval": {
        const allowed = ["operation","approval_id","decision","reason"];
        if (Object.keys(body).some((key) => !allowed.includes(key))) return response(400, { error: "unexpected field" }, corsOrigin);
        if (!operator(user)) return response(403, { error: "JAEO operator role required" }, corsOrigin);
        if (typeof body.approval_id !== "string" || !UUID.test(body.approval_id)
          || !["approved","rejected"].includes(String(body.decision))
          || (body.reason !== undefined && (typeof body.reason !== "string" || body.reason.length > 1000))) {
          return response(400, { error: "invalid approval decision" }, corsOrigin);
        }
        const { data: approval, error: lookupError } = await admin.schema("jarvis_private").from("jaeo_approvals")
          .select("id,task_id,action,resource_id,requested_by,request_hash,status,expires_at")
          .eq("id", body.approval_id).maybeSingle();
        if (lookupError || !approval) return response(404, { error: "approval not found" }, corsOrigin);
        if (approval.status !== "pending" || new Date(approval.expires_at).getTime() <= Date.now()) {
          return response(409, { error: "approval is no longer pending or has expired" }, corsOrigin);
        }
        if (approval.requested_by === user.id) return response(403, { error: "requesters cannot approve their own requests" }, corsOrigin);
        if (isProductionResource(approval.resource_id)) return response(403, { error: "production resources are permanently outside JAEO authority" }, corsOrigin);
        const { data, error } = await admin.schema("jarvis_private").from("jaeo_approvals").update({
          status: body.decision, decided_at: new Date().toISOString(), decided_by_user_id: user.id,
          decided_by: user.id, decision_reason: body.reason ?? null,
        }).eq("id", body.approval_id).eq("status","pending").gt("expires_at",new Date().toISOString())
          .select("id,task_id,action,resource_id,status,requested_at,decided_at,decided_by_user_id,expires_at,request_hash").maybeSingle();
        if (error || !data) return response(409, { error: "approval decision could not be recorded" }, corsOrigin);
        return response(200, { approval: data, note: "Decision recorded; no external action was executed." }, corsOrigin);
      }
      case "add_feedback": {
        const allowed = ["operation","task_id","agent_role","status","payload"];
        if (Object.keys(body).some((key) => !allowed.includes(key))) return response(400, { error: "unexpected field" }, corsOrigin);
        if (typeof body.task_id !== "string" || !UUID.test(body.task_id)
          || typeof body.agent_role !== "string" || !TASK_ROLES.has(body.agent_role)
          || !["queued","running","awaiting_approval","completed","failed","blocked"].includes(String(body.status))
          || !isRecord(body.payload) || new TextEncoder().encode(canonical(body.payload)).byteLength > 16000) {
          return response(400, { error: "invalid feedback" }, corsOrigin);
        }
        const { data: task, error: taskError } = await admin.schema("jarvis_private").from("jaeo_tasks")
          .select("id,requested_by").eq("id", body.task_id).maybeSingle();
        if (taskError || !task || (task.requested_by !== user.id && !operator(user))) return response(404, { error: "task not found" }, corsOrigin);
        const { data, error } = await admin.schema("jarvis_private").from("jaeo_feedback").insert({
          task_id: body.task_id, agent_role: body.agent_role, status: body.status, payload: body.payload,
        }).select("id,task_id,agent_role,status,occurred_at").single();
        if (error || !data) return response(500, { error: "feedback could not be recorded" }, corsOrigin);
        return response(201, { feedback: data }, corsOrigin);
      }
      default:
        return response(400, { error: "unsupported operation" }, corsOrigin);
    }
  } catch {
    return response(500, { error: "JAEO request failed safely" }, corsOrigin);
  }
});
