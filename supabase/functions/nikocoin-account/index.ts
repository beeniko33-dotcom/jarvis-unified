import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const MAX_BODY_BYTES = 1024;

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

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { status: 200, headers: cors(req) });
  if (req.method !== "POST") return reply(req, 405, { error: "method not allowed" });

  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(req, 401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  let secretKeys: Record<string,string> = {};
  try { secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}"); } catch { /* use the legacy service-role fallback */ }\n  const serviceKey = secretKeys.default ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anon || !serviceKey) return reply(req, 503, { error: "rewards service is not configured" });

  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return reply(req, 413, { error: "request too large" });
  let body: Record<string, unknown> = {};
  if (raw.trim()) {
    try {
      body = JSON.parse(raw);
      if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid");
    } catch {
      return reply(req, 400, { error: "invalid JSON" });
    }
  }
  if (Object.keys(body).some((key) => key !== "limit")) return reply(req, 400, { error: "unexpected field" });
  const limit = body.limit === undefined ? 50 : body.limit;
  if (!Number.isInteger(limit) || Number(limit) < 1 || Number(limit) > 100) {
    return reply(req, 400, { error: "limit must be an integer from 1 to 100" });
  }

  const userClient = createClient(url, anon, {
    global: { headers: { Authorization: auth } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userError } = await userClient.auth.getUser(auth.slice("Bearer ".length));
  if (userError || !userData.user) return reply(req, 401, { error: "invalid or expired session" });

  const admin = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const [balance, history] = await Promise.all([
    admin.rpc("jarvis_nikocoin_balance", { p_user_id: userData.user.id }),
    admin.rpc("jarvis_nikocoin_history", { p_user_id: userData.user.id, p_limit: Number(limit) }),
  ]);
  if (balance.error || history.error) return reply(req, 503, { error: "rewards account could not be loaded" });
  return reply(req, 200, {
    balance: balance.data,
    history: history.data,
    rewards_active: false,
    note: "NikoCoin is an internal-only reward unit. It has no cash value, cannot be transferred, and is not an on-chain token.",
  });
});
