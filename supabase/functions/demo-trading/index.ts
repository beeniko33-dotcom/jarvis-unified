import { createClient } from "npm:@supabase/supabase-js@2.45.4";
const URL = Deno.env.get("SUPABASE_URL") ?? "";
const ANON = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const GATE = "https://api.gateio.ws/api/v4";
const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const HEADERS = { "content-type": "application/json", "cache-control": "no-store" };

function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const allowed = ORIGINS.has(origin) || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return allowed ? {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "vary": "Origin",
  } : {};
}
function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...HEADERS, ...cors(req) } });
}
async function authorize(req: Request) {
  const authorization = req.headers.get("authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) return { response: reply(req, 401, { error: "sign_in_required" }) };
  if (!URL || !ANON || !SERVICE) return { response: reply(req, 503, { error: "service_not_configured" }) };
  const userClient = createClient(URL, ANON, { global: { headers: { Authorization: authorization } } });
  const { data, error } = await userClient.auth.getUser();
  if (error || !data.user) return { response: reply(req, 401, { error: "invalid_session" }) };
  const admin = createClient(URL, SERVICE, { auth: { persistSession: false } });
  const { data: allowed, error: allowError } = await admin.from("operator_allowlist")
    .select("user_id").eq("user_id", data.user.id).maybeSingle();
  if (allowError) return { response: reply(req, 503, { error: "operator_check_failed" }) };
  if (!allowed) return { response: reply(req, 403, { error: "operator_not_allowlisted" }) };
  return { user: data.user, admin };
}
async function market() {
  const pairBySymbol: Record<string, string> = {
    BTCUSDT: "BTC_USDT",
    ETHUSDT: "ETH_USDT",
    SOLUSDT: "SOL_USDT",
  };
  const results = await Promise.all(SYMBOLS.map(async (symbol) => {
    try {
      const pair = pairBySymbol[symbol];
      const response = await fetch(
        GATE + "/spot/trades?currency_pair=" + pair + "&limit=10",
        { signal: AbortSignal.timeout(7000), cache: "no-store" },
      );
      if (!response.ok) throw new Error("provider_http_" + response.status);
      const rows = await response.json();
      if (!Array.isArray(rows) || !rows.length) throw new Error("trade_missing");
      const trades = rows.map((item: Record<string, unknown>) => {
        const timeMs = Number(item.create_time_ms ?? (Number(item.create_time) * 1000));
        const price = Number(item.price);
        return { item, timeMs, price };
      }).filter((trade: { item: Record<string, unknown>; timeMs: number; price: number }) =>
        Number.isFinite(trade.timeMs) && trade.timeMs > 0 &&
        Number.isFinite(trade.price) && trade.price > 0
      );
      if (!trades.length) throw new Error("invalid_provider_trade");
      const trade = trades.reduce((latest: typeof trades[number], candidate: typeof trades[number]) =>
        candidate.timeMs > latest.timeMs ? candidate : latest
      );
      const receivedAt = Date.now(), age = receivedAt - trade.timeMs;
      return {
        quote: {
          symbol, price: trade.price, provider: "Gate.io Spot", price_basis: "last_trade",
          trade_id: String(trade.item.id ?? ""),
          provider_timestamp: new Date(trade.timeMs).toISOString(),
          received_at: new Date(receivedAt).toISOString(), quote_age_ms: age,
          stale: age < -5000 || age > 30000,
        },
      };
    } catch (error) {
      return { error: { symbol, reason: error instanceof Error ? error.message : "market_data_unavailable" } };
    }
  }));
  return {
    quotes: results.flatMap((result) => result.quote ? [result.quote] : []),
    errors: results.flatMap((result) => result.error ? [result.error] : []),
  };
}
Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(req) });
  if (!["GET", "POST"].includes(req.method)) return reply(req, 405, { error: "method_not_allowed" });
  const auth = await authorize(req);
  if (auth.response) return auth.response;
  try {
    if (req.method === "GET") {
      const [snapshot, marketResult] = await Promise.all([
        auth.admin.rpc("jarvis_demo_account_snapshot", { p_user_id: auth.user.id }),
        market(),
      ]);
      if (snapshot.error) return reply(req, 503, { error: "demo_account_unavailable" });
      return reply(req, 200, {
        ...snapshot.data,
        quotes: marketResult.quotes,
        market_errors: marketResult.errors,
        fee_rate: 0.001,
        account_type: "demo",
        execution_mode: "paper",
        live_orders: 0,
      });
    }

    const raw = await req.text();
    if (new TextEncoder().encode(raw).byteLength > 2048) return reply(req, 413, { error: "request_too_large" });
    let body: Record<string, unknown>;
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid_object");
      body = parsed as Record<string, unknown>;
    } catch {
      return reply(req, 400, { error: "invalid_json" });
    }
    if (Object.keys(body).some((key) => !["symbol", "side", "quantity", "idempotency_key"].includes(key)))
      return reply(req, 400, { error: "invalid_request_fields" });
    const symbol = String(body.symbol ?? ""), side = String(body.side ?? "");
    const quantity = Number(body.quantity), idempotencyKey = String(body.idempotency_key ?? "");
    if (!SYMBOLS.includes(symbol) || !["buy", "sell"].includes(side) ||
        !Number.isFinite(quantity) || quantity <= 0 || quantity > 100000 ||
        Math.abs(quantity * 1e8 - Math.round(quantity * 1e8)) > 0.00001 ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(idempotencyKey)) {
      return reply(req, 400, { error: "invalid_order_parameters" });
    }
    const marketResult = await market();
    const quote = marketResult.quotes.find((item) => item.symbol === symbol);
    if (!quote) return reply(req, 503, { error: "market_quote_unavailable" });
    if (quote.stale) return reply(req, 409, { error: "market_quote_stale" });
    const { data, error } = await auth.admin.rpc("jarvis_execute_demo_trade", {
      p_user_id: auth.user.id,
      p_symbol: symbol,
      p_side: side,
      p_quantity: quantity,
      p_price: quote.price,
      p_provider_timestamp: quote.provider_timestamp,
      p_idempotency_key: idempotencyKey,
    });
    if (error) {
      const message = String(error.message ?? "");
      const known = [
        "insufficient_demo_cash", "insufficient_demo_position", "per_trade_notional_limit_exceeded",
        "market_price_stale", "unsupported_market_or_side", "invalid_quantity",
      ].find((code) => message.includes(code));
      return reply(req, known ? 409 : 503, { error: known ?? "demo_trade_rejected" });
    }
    return reply(req, 200, { result: data, quote, execution_mode: "paper", live_orders: 0 });
  } catch (error) {
    return reply(req, 502, { error: error instanceof Error ? error.message : "demo_trading_unavailable" });
  }
});
