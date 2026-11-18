import "jsr:@supabase/functions-js/edge-runtime.d.ts";
// Receives paper-trading signal events from the Cloudflare worker (/signals) and stores them as
// research_only rows with no evidence credit. It never places, routes or authorizes an order.
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SECRET_KEYS = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
const SERVICE_ROLE_KEY = SECRET_KEYS.default ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const INGEST_TOKEN = Deno.env.get("JARVIS_INGEST_TOKEN") ?? "";
const MAX_BODY_BYTES = 16 * 1024;
const KINDS = new Set(["signal", "paper_fill", "risk_reject"]);
const INTERVALS = new Set(["1m", "5m", "15m", "1h", "4h", "1d"]);
const DECIMAL = /^-?\d{1,18}(\.\d{1,12})?$/;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
function tokenMatches(supplied: string, expected: string): boolean {
  const a = new TextEncoder().encode(supplied), b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}
function dec(value: unknown, field: string): string {
  const s = String(value ?? "");
  if (!DECIMAL.test(s)) throw new Error(field + "_invalid");
  return s;
}
function text(value: unknown, field: string, max: number): string {
  const s = String(value ?? "").trim();
  if (s.length < 1 || s.length > max) throw new Error(field + "_invalid");
  return s;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY || !INGEST_TOKEN) return json({ error: "server_not_configured" }, 503);
  if (!tokenMatches(req.headers.get("x-jarvis-ingest-token") ?? "", INGEST_TOKEN)) return json({ error: "unauthorized_ingest_source" }, 401);
  let body: Record<string, unknown>;
  try {
    const raw = await req.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return json({ error: "payload_too_large" }, 413);
    body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("not_object");
  } catch { return json({ error: "invalid_json" }, 400); }

  let row: Record<string, unknown>;
  try {
    const kind = String(body.kind ?? "");
    if (!KINDS.has(kind)) throw new Error("kind_invalid");
    const side = body.side === null || body.side === undefined ? null : String(body.side);
    if (side !== null && side !== "buy" && side !== "sell") throw new Error("side_invalid");
    const symbol = text(body.symbol, "symbol", 24).toUpperCase();
    if (!/^[A-Z0-9._-]{3,24}$/.test(symbol)) throw new Error("symbol_invalid");
    const interval = text(body.interval, "interval", 8);
    if (!INTERVALS.has(interval)) throw new Error("interval_invalid");
    const eventTime = new Date(String(body.event_time ?? ""));
    if (!Number.isFinite(eventTime.getTime())) throw new Error("event_time_invalid");
    const price = dec(body.price, "price");
    if (Number(price) <= 0) throw new Error("price_invalid");
    const analysis: Record<string, unknown> = { event_kind: kind, signal: side };
    if (body.fast_sma !== undefined) analysis.fast_sma = dec(body.fast_sma, "fast_sma");
    if (body.slow_sma !== undefined) analysis.slow_sma = dec(body.slow_sma, "slow_sma");
    const paper: Record<string, unknown> = { entries_allowed: body.entries_allowed === true };
    if (body.quantity !== undefined) paper.quantity = dec(body.quantity, "quantity");
    if (body.net_pnl !== undefined) paper.net_pnl = dec(body.net_pnl, "net_pnl");
    const risk: Record<string, unknown> = {};
    if (body.reason !== undefined) risk.reason = text(body.reason, "reason", 64);
    row = {
      idempotency_key: text(body.idempotency_key, "idempotency_key", 160),
      instrument: symbol,
      asset_class: "crypto",
      direction: side === "buy" ? "long" : "neutral",
      timeframe: interval,
      strategy_id: text(body.strategy_id, "strategy_id", 64),
      strategy_version: text(body.strategy_version, "strategy_version", 32),
      created_at: eventTime.toISOString(),
      provider: "binance-public",
      quote: { price },
      analysis, risk, paper_execution: paper,
    };
  } catch (e) { return json({ error: e instanceof Error ? e.message : "signal_invalid" }, 400); }

  const upstream = await fetch(SUPABASE_URL.replace(/\/$/, "") + "/rest/v1/rpc/jarvis_ingest_market_signal", {
    method: "POST",
    headers: { apikey: SERVICE_ROLE_KEY, "content-type": "application/json" },
    body: JSON.stringify({ p_signal: row }),
  });
  if (!upstream.ok) return json({ error: "signal_persistence_failed", upstream_status: upstream.status }, 502);
  return json(await upstream.json(), 202);
});
