import { createClient, type User } from "npm:@supabase/supabase-js@2.45.4";

const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const TASK_ROLES = new Set(["orchestrator","engineering","database","infrastructure","security","qa","research","release","audit"]);
const APPROVAL_ACTIONS = new Set(["change_code","change_schema","change_secret","provision_resource","create_cron","deploy_preview","merge_pull_request"]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_BODY = 12_000;

function json(status: number, body: unknown, origin?: string) {
  const headers: Record<string,string> = { ...JSON_HEADERS };
  if (origin) Object.assign(headers, {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "access-control-max-age": "600",
    "vary": "Origin",
  });
  return new Response(JSON.stringify(body), { status, headers });
}
function canonical(value: unknown): string {
  if (value === undefined) return "null";
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  const obj = value as Record<string,unknown>;
  return "{" + Object.keys(obj).sort().map((key) => JSON.stringify(key) + ":" + canonical(obj[key])).join(",") + "}";
}
async function sha256(value: unknown): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value)));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2,"0")).join("");
}
function record(value: unknown): value is Record<string,unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function envApiKey(legacyName: string, modernName: string): string {
  const modern = Deno.env.get(modernName);
  if (modern) {
    try {
      const parsed: unknown = JSON.parse(modern);
      if (record(parsed) && typeof parsed.default === "string" && parsed.default.length > 0) return parsed.default;
    } catch {
      if (modern.length > 0) return modern;
    }
  }
  return Deno.env.get(legacyName) ?? "";
}
function isOperator(user: User) { return user.app_metadata?.jaeo_operator === true; }
function mapError(error: { code?: string } | null) {
  if (error?.code === "42501") return 403;
  if (error?.code === "P0002") return 404;
  if (error?.code === "23505") return 409;
  if (error?.code === "22023") return 400;
  if (error?.code === "23514") return 409;
  return 500;
}

Deno.serve(async (req: Request) => {
  const origins = new Set((Deno.env.get("JAEO_ALLOWED_ORIGINS") ?? "").split(",").map((v) => v.trim()).filter(Boolean));
  const origin = req.headers.get("origin") ?? "";
  const portalOrigin = /^https:\/\/(?:[a-z0-9-]+\.)?jarvis-unified-portal\.pages\.dev$/.test(origin);
  const corsOrigin = origins.has(origin) || portalOrigin ? origin : undefined;
  if (req.method === "OPTIONS") return corsOrigin
    ? new Response("ok", { status: 204, headers: { "access-control-allow-origin": origin, "access-control-allow-methods": "POST, OPTIONS", "access-control-allow-headers": "authorization, apikey, content-type, x-client-info", "access-control-max-age": "600", "vary": "Origin" } })
    : json(403, { error: "origin not allowed" });
  if (req.method !== "POST") return json(405, { error: "method not allowed" }, corsOrigin);
  const authorization = req.headers.get("authorization") ?? "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!token) return json(401, { error: "authentication required" }, corsOrigin);

  const url = Deno.env.get("SUPABASE_URL");
  const anonKey = envApiKey("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEYS");
  const serviceKey = envApiKey("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEYS");
  if (!url || !anonKey || !serviceKey) return json(503, { error: "JAEO service is not configured" }, corsOrigin);
  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY) return json(413, { error: "request too large" }, corsOrigin);
  let body: Record<string,unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!record(parsed)) throw new Error("object required");
    body = parsed;
  } catch { return json(400, { error: "invalid JSON object" }, corsOrigin); }

  const userClient = createClient(url, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: authData, error: authError } = await userClient.auth.getUser(token);
  if (authError || !authData.user) return json(401, { error: "invalid or expired session" }, corsOrigin);
  const user = authData.user;
  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

  const operation = body.operation;
  let payload: Record<string,unknown> = {};
  if (operation === "create_task") {
    if (Object.keys(body).some((k) => !["operation","idempotency_key","title","description","agent_role","workspace_scope"].includes(k))
      || typeof body.idempotency_key !== "string" || body.idempotency_key.length < 8 || body.idempotency_key.length > 128
      || typeof body.title !== "string" || body.title.trim().length < 1 || body.title.length > 200
      || typeof body.description !== "string" || body.description.length > 4000
      || typeof body.agent_role !== "string" || !TASK_ROLES.has(body.agent_role)
      || !["all","core",undefined].includes(body.workspace_scope as string | undefined)) {
      return json(400, { error: "invalid task fields" }, corsOrigin);
    }
    payload = { idempotency_key: body.idempotency_key, title: body.title.trim(), description: body.description,
      agent_role: body.agent_role, workspace_scope: body.workspace_scope ?? "all" };
  } else if (operation === "list_tasks") {
    if (Object.keys(body).length !== 1) return json(400, { error: "unexpected field" }, corsOrigin);
  } else if (operation === "list_approvals") {
    if (Object.keys(body).length !== 1) return json(400, { error: "unexpected field" }, corsOrigin);
  } else if (operation === "request_approval") {
    if (Object.keys(body).some((k) => !["operation","task_id","action","resource_id","request"].includes(k))
      || typeof body.task_id !== "string" || !UUID.test(body.task_id)
      || typeof body.action !== "string" || !APPROVAL_ACTIONS.has(body.action)
      || typeof body.resource_id !== "string" || !body.resource_id.trim() || body.resource_id.length > 256
      || !record(body.request) || new TextEncoder().encode(canonical(body.request)).byteLength > 8192) {
      return json(400, { error: "invalid approval request" }, corsOrigin);
    }
    const requestHash = await sha256({ action: body.action, resource_id: body.resource_id.trim(), request: body.request });
    payload = { task_id: body.task_id, action: body.action, resource_id: body.resource_id.trim(), request: body.request, request_hash: requestHash };
  } else if (operation === "decide_approval") {
    if (!isOperator(user)) return json(403, { error: "JAEO operator role required" }, corsOrigin);
    if (Object.keys(body).some((k) => !["operation","approval_id","decision","reason"].includes(k))
      || typeof body.approval_id !== "string" || !UUID.test(body.approval_id)
      || !["approved","rejected"].includes(String(body.decision))
      || (body.reason !== undefined && (typeof body.reason !== "string" || body.reason.length > 1000))) {
      return json(400, { error: "invalid approval decision" }, corsOrigin);
    }
    payload = { approval_id: body.approval_id, decision: body.decision, reason: body.reason ?? "" };
  } else if (operation === "add_feedback") {
    if (Object.keys(body).some((k) => !["operation","task_id","agent_role","status","payload"].includes(k))
      || typeof body.task_id !== "string" || !UUID.test(body.task_id)
      || typeof body.agent_role !== "string" || !TASK_ROLES.has(body.agent_role)
      || !["queued","running","awaiting_approval","completed","failed","blocked"].includes(String(body.status))
      || !record(body.payload) || new TextEncoder().encode(canonical(body.payload)).byteLength > 16000) {
      return json(400, { error: "invalid feedback" }, corsOrigin);
    }
    payload = { task_id: body.task_id, agent_role: body.agent_role, status: body.status, payload: body.payload };
  } else {
    return json(400, { error: "unsupported operation" }, corsOrigin);
  }

  const { data, error } = await admin.rpc("jaeo_operator_api", {
    p_operation: String(operation), p_user_id: user.id, p_is_operator: isOperator(user), p_payload: payload,
  });
  if (error) return json(mapError(error), { error: "JAEO operation was rejected or could not be completed", code: error.code ?? "unknown" }, corsOrigin);
  return json(operation === "create_task" || operation === "request_approval" || operation === "add_feedback" ? 201 : 200, data, corsOrigin);
});
