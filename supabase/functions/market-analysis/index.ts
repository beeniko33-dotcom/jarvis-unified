import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
let SECRET_KEYS: Record<string, string> = {};
try {
  SECRET_KEYS = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
} catch {
  SECRET_KEYS = {};
}
const SERVICE_ROLE_KEYS = [...new Set([
  SECRET_KEYS.default,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"),
  Deno.env.get("SERVICE_ROLE_KEY"),
].filter((key): key is string => typeof key === "string" && key.length > 0))];
const SERVICE_ROLE_KEY = SERVICE_ROLE_KEYS[0] ?? "";
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const INGEST_TOKEN = Deno.env.get("JARVIS_INGEST_TOKEN") ?? "";
const GATE_BASE = "https://api.gateio.ws/api/v4";
const PAIR = "BTC_USDT";
const SYMBOL = "BTCUSDT";
const INTERVAL = "5m";
const STRATEGY_ID = "btc-5m-sma20-sma50-rsi14-wilder";
const STRATEGY_VERSION = "1.0.0";
const MAX_AGE_MS = 360_000;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  const o = value as Record<string, unknown>;
  return "{" + Object.keys(o).sort().map(k => JSON.stringify(k) + ":" + canonical(o[k])).join(",") + "}";
}
async function sha256(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, "0")).join("");
}
async function getJson(url: string): Promise<any> {
  const response = await fetch(url, {
    headers: { "accept": "application/json", "cache-control": "no-cache" },
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error("market_provider_http_" + response.status);
  return await response.json();
}
function tokenMatches(supplied: string, expected: string): boolean {
  const a = new TextEncoder().encode(supplied), b = new TextEncoder().encode(expected);
  if (!a.length || a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
}

async function verifiedUserId(req: Request): Promise<string> {
  const authorization = req.headers.get("authorization") ?? "";
  if (!authorization.startsWith("Bearer ") || !SUPABASE_URL || !ANON_KEY) return "";
  const baseUrl = SUPABASE_URL.endsWith("/") ? SUPABASE_URL.slice(0, -1) : SUPABASE_URL;
  const response = await fetch(baseUrl + "/auth/v1/user", {
    method: "GET",
    headers: { "apikey": ANON_KEY, "authorization": authorization },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) return "";
  const user = await response.json();
  return user && typeof user.id === "string" ? user.id : "";
}
async function isAllowlistedOperator(userId: string): Promise<boolean> {
  const url = SUPABASE_URL.replace(/\/$/, "") +
    "/rest/v1/operator_allowlist?user_id=eq." + encodeURIComponent(userId) + "&select=user_id&limit=1";
  const response = await fetch(url, {
    headers: { "apikey": SERVICE_ROLE_KEY, "authorization": "Bearer " + SERVICE_ROLE_KEY },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) throw new Error("operator_allowlist_check_failed");
  const rows = await response.json();
  return Array.isArray(rows) && rows.length === 1;
}
function number(value: unknown, label: string): number {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error("invalid_" + label);
  return n;
}
function sma(values: number[], period: number): number {
  if (values.length < period) throw new Error("insufficient_candle_history");
  return values.slice(-period).reduce((a, b) => a + b, 0) / period;
}
function rsi(values: number[], period = 14): number {
  if (values.length <= period) throw new Error("insufficient_rsi_history");
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const delta = values[i] - values[i - 1];
    if (delta > 0) avgGain += delta;
    else avgLoss -= delta;
  }
  avgGain /= period;
  avgLoss /= period;
  for (let i = period + 1; i < values.length; i++) {
    const delta = values[i] - values[i - 1];
    const gain = Math.max(delta, 0);
    const loss = Math.max(-delta, 0);
    avgGain = ((avgGain * (period - 1)) + gain) / period;
    avgLoss = ((avgLoss * (period - 1)) + loss) / period;
  }
  if (avgLoss === 0) return avgGain === 0 ? 50 : 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}
function parseCandle(row: unknown): { openTime: number; closeTime: number; open: number; high: number; low: number; close: number; volume: number; quoteVolume: number } {
  if (!Array.isArray(row) || row.length < 7) throw new Error("malformed_gate_candle");
  const openTime = number(row[0], "open_time") * 1000;
  const c = {
    openTime,
    closeTime: openTime + 300_000,
    quoteVolume: number(row[1], "quote_volume"),
    close: number(row[2], "close"),
    high: number(row[3], "high"),
    low: number(row[4], "low"),
    open: number(row[5], "open"),
    volume: number(row[6], "volume"),
  };
  if (c.open <= 0 || c.high <= 0 || c.low <= 0 || c.close <= 0 || c.volume < 0 ||
      c.high < Math.max(c.open, c.close, c.low) || c.low > Math.min(c.open, c.close, c.high)) {
    throw new Error("ohlc_invariant_failed");
  }
  return c;
}
async function rpc(name: string, body: unknown): Promise<any> {
  const response = await fetch(SUPABASE_URL.replace(/\/$/, "") + "/rest/v1/rpc/" + name, {
    method: "POST",
    headers: {
      "apikey": SERVICE_ROLE_KEY,
      "authorization": "Bearer " + SERVICE_ROLE_KEY,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(name + "_failed_" + response.status);
  return await response.json();
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) return json({ error: "server_not_configured" }, 503);
  // Machine callers use a dedicated shared collector token; the service-role
  // key fallback preserves the existing GitHub Actions scheduler. Both checks
  // are performed inside the function because gateway JWT verification is off.
  const suppliedApiKey = req.headers.get("apikey") ?? "";
  const machineAuthorized =
    (!!INGEST_TOKEN && tokenMatches(req.headers.get("x-jarvis-ingest-token") ?? "", INGEST_TOKEN)) ||
    SERVICE_ROLE_KEYS.some((key) => tokenMatches(suppliedApiKey, key));
  try {
    if (!machineAuthorized) {
      const userId = await verifiedUserId(req);
      if (!userId) return json({ error: "authenticated_operator_required" }, 401);
      if (!(await isAllowlistedOperator(userId))) {
        return json({ error: "operator_not_allowlisted" }, 403);
      }
    }
    const [clock, rawKlines] = await Promise.all([
      getJson(GATE_BASE + "/spot/time"),
      getJson(GATE_BASE + "/spot/candlesticks?currency_pair=" + PAIR + "&interval=" + INTERVAL + "&limit=100"),
    ]);
    const receivedAt = Date.now();
    const serverTime = number(clock.server_time, "server_time");
    if (!Array.isArray(rawKlines) || rawKlines.length < 60) throw new Error("insufficient_provider_candles");
    const parsed = rawKlines.map(parseCandle).sort((a, b) => a.openTime - b.openTime);
    const completed = parsed.filter(c => c.closeTime <= serverTime);
    if (completed.length < 60) throw new Error("insufficient_completed_candles");
    const latest = completed[completed.length - 1];
    const ageMs = serverTime - latest.closeTime;
    if (ageMs < 0 || ageMs > MAX_AGE_MS) throw new Error("latest_completed_candle_stale_or_future");
    if (Math.abs(receivedAt - serverTime) > 30_000) throw new Error("local_clock_skew_exceeds_30s");

    const closes = completed.map(c => c.close);
    const sma20 = sma(closes, 20);
    const sma50 = sma(closes, 50);
    const rsi14 = rsi(closes, 14);
    const previousClose = closes[closes.length - 2];
    const return5mPct = (latest.close / previousClose - 1) * 100;
    const trend = sma20 > sma50 ? "bullish" : sma20 < sma50 ? "bearish" : "flat";
    let direction = "neutral";
    let rationale = "Trend and momentum conditions are not aligned; no directional bias.";
    if (trend === "bullish" && latest.close > sma20 && rsi14 >= 50 && rsi14 < 70) {
      direction = "long";
      rationale = "SMA20 is above SMA50, close is above SMA20, and RSI14 is in the non-extreme bullish band.";
    } else if (trend === "bearish" && latest.close < sma20 && rsi14 > 30 && rsi14 <= 50) {
      direction = "short";
      rationale = "SMA20 is below SMA50, close is below SMA20, and RSI14 is in the non-extreme bearish band.";
    }

    const rawPayload = { candles: rawKlines };
    const digest = await sha256(canonical(rawPayload));
    const eventTime = new Date(latest.closeTime).toISOString();
    const receivedIso = new Date(receivedAt).toISOString();
    const quoteAgeSeconds = Math.max(0, (serverTime - latest.closeTime) / 1000);
    const observation = {
      source_id: "gateio-spot-public-rest:" + PAIR,
      event_time: eventTime,
      received_at: receivedIso,
      symbol: "BTCUSDT",
      timeframe: INTERVAL,
      schema_version: 1,
      content_hash: digest,
      values_json: {
        provider: "Gate.io",
        provider_endpoint: GATE_BASE + "/spot/candlesticks",
        provider_pair: PAIR,
        market_type: "spot",
        klines: rawKlines,
        candle: { ...latest, open_time: new Date(latest.openTime).toISOString(), close_time: eventTime },
        indicators: { sma20, sma50, rsi14, return_5m_pct: return5mPct, trend },
        quote_age_seconds: quoteAgeSeconds,
        provider_server_time: new Date(serverTime).toISOString(),
        collector_received_at: receivedIso,
        raw_payload: rawPayload,
        trust_classification: "candidate_unverified",
        provenance_verified: false,
        evidence_credit: false,
        analysis_basis: "completed_5m_candles",
      },
      out_of_order: false,
      stale: quoteAgeSeconds > 120,
      clock_skew: Math.abs(receivedAt - serverTime) > 10_000,
    };
    const observationResult = await rpc("jarvis_ingest_market_observations", { p_observations: [observation] });
    const signal = {
      idempotency_key: "gateio-btc-5m-sma20-50-rsi14:" + latest.closeTime,
      instrument: SYMBOL,
      asset_class: "crypto",
      direction,
      timeframe: INTERVAL,
      strategy_id: STRATEGY_ID,
      strategy_version: STRATEGY_VERSION,
      provider: "Gate.io",
      created_at: receivedIso,
      quote: {
        price_basis: "last_completed_candle_close",
        mid: latest.close,
        bid: null,
        ask: null,
        provider_timestamp: eventTime,
        collector_received_at: receivedIso,
        quote_age_seconds: quoteAgeSeconds,
      },
      analysis: {
        trend,
        sma20,
        sma50,
        rsi14,
        return_5m_pct: return5mPct,
        completed_candles_used: completed.length,
        rationale,
        source_endpoint: GATE_BASE + "/spot/candlesticks",
        market_data_trust: "unverified_market_data",
        evidence_credit: false,
      },
      risk: {
        gate: "blocked_research_only",
        proposed_position_size: 0,
        order_authorized: false,
        reason: "Unverified public market data; no validated paper-session runtime or owner release.",
      },
      paper_execution: {
        enabled: false,
        orders_created: 0,
        positions_opened: 0,
        live_execution: false,
      },
    };
    const signalResult = await rpc("jarvis_ingest_market_signal", { p_signal: signal });
    return json({
      ok: true,
      provider: "Gate.io public spot REST",
      instrument: SYMBOL,
      timeframe: INTERVAL,
      observation: observationResult,
      signal: signalResult,
      analysis: { direction, trend, close: latest.close, sma20, sma50, rsi14, candle_time: eventTime, quote_age_seconds: quoteAgeSeconds },
      trust: "candidate_unverified",
      evidence_credit: false,
      paper_execution: "disabled",
      live_orders: 0,
    }, 200);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "market_analysis_failed" }, 502);
  }
});
