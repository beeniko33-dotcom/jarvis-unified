import { createClient, type User } from "npm:@supabase/supabase-js@2.119.2";

const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const TASK_ROLES = new Set(["orchestrator","engineering","database","infrastructure","security","qa","research","release","audit"]);
const APPROVAL_ACTIONS = new Set(["change_code","change_schema","provision_resource","create_cron","deploy_preview","merge_pull_request"]);
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
function containsSensitiveMaterial(value: unknown): boolean {
  const sensitiveKey = /secret|password|token|api.?key|authorization|private.?key|credential|mnemonic|seed.?phrase/i;
  const secretValue = /(?:sb_secret_|sb_publishable_|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})/;
  if (typeof value === "string") return secretValue.test(value);
  if (Array.isArray(value)) return value.some(containsSensitiveMaterial);
  if (record(value)) return Object.entries(value).some(([key, child]) => sensitiveKey.test(key) || containsSensitiveMaterial(child));
  return false;
}
// First-owner bootstrap is pinned to the one existing, email-confirmed QA account.
// This avoids unsafe direct writes to auth.users and avoids requiring dashboard metadata edits.
const JAEO_BOOTSTRAP_OWNER_USER_ID = "0d27e78c-935c-4be7-8d0a-bbc7ce846bce";
function isOwner(user: User) { return user.id === JAEO_BOOTSTRAP_OWNER_USER_ID || user.app_metadata?.jaeo_owner === true; }
function isOperator(user: User) { return user.app_metadata?.jaeo_operator === true || isOwner(user); }
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
  if (operation === "list_operator_users") {
    if (!isOwner(user) || Object.keys(body).length !== 1) return json(403, { error: "JAEO owner role required" }, corsOrigin);
    const { data, error } = await admin.auth.admin.listUsers({ page: 1, perPage: 200 });
    if (error) return json(502, { error: "Could not load QA account directory" }, corsOrigin);
    return json(200, { users: data.users.map((entry) => ({
      id: entry.id, email: entry.email ?? null, created_at: entry.created_at,
      jaeo_operator: entry.app_metadata?.jaeo_operator === true,
      email_confirmed: Boolean(entry.email_confirmed_at),
    })) }, corsOrigin);
  }
  if (operation === "grant_operator") {
    if (!isOwner(user)) return json(403, { error: "JAEO owner role required" }, corsOrigin);
    if (Object.keys(body).some((k) => !["operation", "target_user_id"].includes(k))
      || typeof body.target_user_id !== "string" || !UUID.test(body.target_user_id)
      || body.target_user_id === user.id) {
      return json(400, { error: "Choose another existing QA user; self-provisioning is not allowed" }, corsOrigin);
    }
    const { data: targetData, error: targetError } = await admin.auth.admin.getUserById(body.target_user_id);
    if (targetError || !targetData.user) return json(404, { error: "QA user not found" }, corsOrigin);
    const target = targetData.user;
    if (!target.email_confirmed_at) return json(409, { error: "The target must confirm their email before operator access can be granted" }, corsOrigin);
    if (target.app_metadata?.jaeo_operator === true) return json(409, { error: "This account is already a JAEO operator" }, corsOrigin);
    const previousMetadata = { ...(target.app_metadata ?? {}) };
    const { data: updatedData, error: updateError } = await admin.auth.admin.updateUserById(target.id, {
      app_metadata: { ...previousMetadata, jaeo_operator: true },
    });
    if (updateError || !updatedData.user) return json(502, { error: "Could not update trusted operator role" }, corsOrigin);
    const { data: auditId, error: auditError } = await admin.rpc("jaeo_record_operator_admin_event", {
      p_actor_id: user.id, p_target_id: target.id, p_action: "grant_operator",
      p_target_email: target.email ?? null, p_detail: { source: "jaeo_console", role: "jaeo_operator" },
    });
    if (auditError || !auditId) {
      await admin.auth.admin.updateUserById(target.id, { app_metadata: previousMetadata });
      return json(502, { error: "Operator grant was rolled back because its audit record could not be saved" }, corsOrigin);
    }
    return json(200, { user: { id: target.id, email: target.email ?? null, jaeo_operator: true }, audit_id: auditId }, corsOrigin);
  }
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
      || !record(body.request) || containsSensitiveMaterial(body.request)
      || new TextEncoder().encode(canonical(body.request)).byteLength > 8192) {
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
