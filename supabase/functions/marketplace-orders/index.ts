import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const permitted = ALLOWED_ORIGINS.has(origin) || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return permitted ? {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "access-control-max-age": "86400",
    "vary": "Origin",
  } : {};
}
function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...cors(req) } });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { status: 200, headers: cors(req) });
  if (req.method !== "POST") return reply(req, 405, { error: "method not allowed" });
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(req, 401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  let secretKeys: Record<string,string> = {};
  try { secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}"); } catch { /* fall back to service-role env */ }
  const serviceKey = secretKeys.default ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anon || !serviceKey) return reply(req, 503, { error: "order service is not configured" });

  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > 2048) return reply(req, 413, { error: "request too large" });
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid");
  } catch {
    return reply(req, 400, { error: "invalid JSON" });
  }
  const allowed = ["listing_id","quantity","idempotency_key","affiliate_code"];
  if (Object.keys(body).some((key) => !allowed.includes(key))) return reply(req, 400, { error: "unexpected field" });
  if (typeof body.listing_id !== "string" || !UUID.test(body.listing_id)
      || typeof body.idempotency_key !== "string" || !UUID.test(body.idempotency_key)
      || !Number.isInteger(body.quantity) || Number(body.quantity) < 1 || Number(body.quantity) > 1000
      || (body.affiliate_code !== undefined && body.affiliate_code !== null
          && (typeof body.affiliate_code !== "string" || body.affiliate_code.length > 64))) {
    return reply(req, 400, { error: "invalid order request" });
  }

  const userClient = createClient(url, anon, {
    global: { headers: { Authorization: auth } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userError } = await userClient.auth.getUser(auth.slice("Bearer ".length));
  if (userError || !userData.user) return reply(req, 401, { error: "invalid or expired session" });

  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data, error } = await admin.rpc("marketplace_create_order_for_user", {
    p_buyer_id: userData.user.id,
    p_listing_id: body.listing_id,
    p_quantity: Number(body.quantity),
    p_affiliate_code: body.affiliate_code ?? null,
    p_idempotency_key: body.idempotency_key,
  });
  if (error) {
    if (error.code === "P0002") return reply(req, 404, { error: "listing is unavailable" });
    if (error.code === "42501") return reply(req, 403, { error: "seller cannot purchase their own listing" });
    if (error.code === "22023") return reply(req, 400, { error: "order validation failed" });
    return reply(req, 503, { error: "order intent could not be created" });
  }
  return reply(req, 200, data);
});
