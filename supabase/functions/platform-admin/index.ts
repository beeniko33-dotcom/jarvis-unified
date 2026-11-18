import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const MAX_BODY_BYTES = 4096;

function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const permitted = ALLOWED_ORIGINS.has(origin)
    || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return permitted ? {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "access-control-max-age": "86400",
    "vary": "Origin",
  } : {};
}

function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...cors(req) },
  });
}

async function authorize(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(req, 401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  let secretKeys: Record<string,string> = {};
  try { secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}"); } catch { /* use the legacy service-role fallback */ }\n  const serviceKey = secretKeys.default ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anon || !serviceKey) return reply(req, 503, { error: "admin service is not configured" });

  const userClient = createClient(url, anon, {
    global: { headers: { Authorization: auth } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await userClient.auth.getUser(auth.slice('Bearer '.length));
  if (error || !data.user) return reply(req, 401, { error: "invalid or expired session" });

  const admin = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: allowed, error: allowError } = await admin
    .from("operator_allowlist")
    .select("user_id")
    .eq("user_id", data.user.id)
    .maybeSingle();
  if (allowError) return reply(req, 503, { error: "operator authorization lookup failed" });
  if (!allowed) return reply(req, 403, { error: "not an authorized operator" });
  return { userId: data.user.id, admin };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { status: 200, headers: cors(req) });
  if (req.method !== "POST") return reply(req, 405, { error: "method not allowed" });

  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return reply(req, 413, { error: "request too large" });
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid");
  } catch {
    return reply(req, 400, { error: "invalid JSON" });
  }

  const auth = await authorize(req);
  if (auth instanceof Response) return auth;

  if (body.action === "list_pending") {
    if (Object.keys(body).some((key) => key !== "action")) return reply(req, 400, { error: "unexpected field" });
    const [orgs, sellers] = await Promise.all([
      auth.admin.from("career_organizations")
        .select("id,name,website,country_code,verification_status,created_at")
        .eq("verification_status", "pending").order("created_at", { ascending: true }).limit(100),
      auth.admin.from("marketplace_sellers")
        .select("id,display_name,country_code,description,verification_status,created_at")
        .eq("verification_status", "pending").order("created_at", { ascending: true }).limit(100),
    ]);
    if (orgs.error || sellers.error) return reply(req, 503, { error: "pending verification queue unavailable" });
    return reply(req, 200, { career_organizations: orgs.data ?? [], marketplace_sellers: sellers.data ?? [] });
  }

  if (body.action === "verify_entity") {
    const allowedKeys = ["action", "entity_type", "entity_id", "status", "reason"];
    if (Object.keys(body).some((key) => !allowedKeys.includes(key))) return reply(req, 400, { error: "unexpected field" });
    const { entity_type, entity_id, status, reason } = body;
    if (entity_type !== "career_organization" && entity_type !== "marketplace_seller") {
      return reply(req, 400, { error: "unsupported entity_type" });
    }
    if (typeof entity_id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(entity_id)) {
      return reply(req, 400, { error: "invalid entity_id" });
    }
    if (status !== "verified" && status !== "rejected" && status !== "suspended") {
      return reply(req, 400, { error: "invalid verification status" });
    }
    if (typeof reason !== "string" || reason.trim().length < 5 || reason.length > 1000) {
      return reply(req, 400, { error: "a reason of 5-1000 characters is required" });
    }
    const { data, error } = await auth.admin.rpc("jarvis_platform_admin_verify_entity", {
      p_actor_id: auth.userId,
      p_entity_type: entity_type,
      p_entity_id: entity_id,
      p_status: status,
      p_reason: reason.trim(),
    });
    if (error) {
      if (error.code === "P0002") return reply(req, 404, { error: "verification target not found" });
      if (error.code === "42501") return reply(req, 403, { error: "operator authorization failed" });
      return reply(req, 400, { error: "verification decision could not be recorded" });
    }
    return reply(req, 200, { result: data });
  }

  return reply(req, 400, { error: "unknown action" });
});
