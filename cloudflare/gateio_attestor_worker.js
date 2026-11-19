const SOURCE = "gateio-spot-public-rest-v1";
const VERIFIER_ID = "jarvis-independent-gateio-verifier-v1";
const BASE = "https://api.gateio.ws/api/v4";
const encoder = new TextEncoder();

function base64(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = stable(value[key]);
    return out;
  }
  return value;
}

async function getJson(path) {
  const response = await fetch(BASE + path, {
    headers: {
      "accept": "application/json",
      "user-agent": "JarvisIndependentVerifier/1.0"
    },
    redirect: "manual",
    signal: AbortSignal.timeout(10000)
  });
  if (response.status >= 300 && response.status < 400) {
    throw new Error("Gate.io redirect rejected");
  }
  if (!response.ok) throw new Error("Gate.io public endpoint HTTP " + response.status);
  const url = new URL(response.url);
  if (url.hostname !== "api.gateio.ws" || url.protocol !== "https:") {
    throw new Error("unexpected Gate.io response host");
  }
  const raw = await response.text();
  return { value: JSON.parse(raw), raw };
}

function positive(value, label) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) throw new Error(label + " invalid");
  return String(value);
}

async function sha256Hex(text) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(text)));
  return Array.from(digest).map(x => x.toString(16).padStart(2, "0")).join("");
}

async function attest(env) {
  const started = Date.now();
  const server = await getJson("/spot/time");
  const serverMs = Number(server.value.server_time);
  if (!Number.isSafeInteger(serverMs) || serverMs < 1000000000000) {
    throw new Error("Gate.io server time malformed");
  }
  const serverSeconds = Math.floor(serverMs / 1000);

  const candleQuery = new URLSearchParams({
    currency_pair: "BTC_USDT",
    interval: "5m",
    limit: "100"
  });
  const candles = await getJson("/spot/candlesticks?" + candleQuery.toString());
  if (!Array.isArray(candles.value)) throw new Error("Gate.io candles malformed");

  const parsed = [];
  for (const row of candles.value) {
    if (!Array.isArray(row) || row.length < 6) throw new Error("Gate.io candle row malformed");
    const start = Number(row[0]);
    const close = positive(row[2], "candle close");
    if (!Number.isSafeInteger(start)) throw new Error("Gate.io candle time malformed");
    const end = start + 300;
    if (end <= serverSeconds) parsed.push({ start, end, close });
  }
  parsed.sort((a, b) => a.start - b.start);

  const unique = [];
  for (const item of parsed) {
    const last = unique[unique.length - 1];
    if (last && last.start === item.start) {
      if (last.close !== item.close || last.end !== item.end) {
        throw new Error("conflicting duplicate candles");
      }
      continue;
    }
    unique.push(item);
  }
  if (unique.length < 50) throw new Error("fewer than 50 completed candles");
  const history = unique.slice(-50);
  for (let i = 1; i < history.length; i++) {
    if (history[i].start - history[i - 1].start !== 300) {
      throw new Error("candle history gap");
    }
  }

  const latest = history[history.length - 1];
  const age = serverSeconds - latest.end;
  if (age < 0 || age > 480) throw new Error("latest completed candle stale");

  const bookQuery = new URLSearchParams({ currency_pair: "BTC_USDT", limit: "1" });
  const book = await getJson("/spot/order_book?" + bookQuery.toString());
  const bids = book.value?.bids;
  const asks = book.value?.asks;
  if (!Array.isArray(bids) || !bids.length || !Array.isArray(asks) || !asks.length ||
      !Array.isArray(bids[0]) || bids[0].length < 2 ||
      !Array.isArray(asks[0]) || asks[0].length < 2) {
    throw new Error("Gate.io top-of-book malformed");
  }
  const bid = Number(positive(bids[0][0], "best bid"));
  const ask = Number(positive(asks[0][0], "best ask"));
  if (bid > ask) throw new Error("crossed order book");

  const received = new Date().toISOString();
  const observation = {
    provider: "Gate.io",
    source: SOURCE,
    instrument: "BTC_USDT",
    interval: "5m",
    complete: true,
    event_time: new Date(latest.end * 1000).toISOString(),
    received_at: received,
    clock_skew_ms: started - serverMs,
    bid: String(bid),
    ask: String(ask),
    closes: history.map(x => x.close),
    raw_payload_sha256: await sha256Hex(server.raw + "\n" + candles.raw + "\n" + book.raw),
    provider_server_time: new Date(serverMs).toISOString(),
    provider_candle_start: latest.start,
    provider_candle_end: latest.end,
    provider_orderbook_update_id: book.value.id ?? null,
    verifier_observed_at: received
  };
  const signature = await crypto.subtle.sign(
    { name: "Ed25519" },
    env.JARVIS_GATEIO_SIGNING_KEY,
    encoder.encode(JSON.stringify(stable(observation)))
  );
  return {
    ...observation,
    trust_attestation: {
      verifier_id: VERIFIER_ID,
      signature: base64(signature)
    },
    provenance_verified: false,
    evidence_credit: false
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "GET" || url.pathname !== "/v1/attestation") {
      return new Response("not found", { status: 404 });
    }
    try {
      const result = await attest(env);
      return new Response(JSON.stringify(result), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "cache-control": "no-store",
          "x-content-type-options": "nosniff"
        }
      });
    } catch (error) {
      return new Response(JSON.stringify({
        ok: false,
        error: error instanceof Error ? error.message : "attestation failed"
      }), {
        status: 503,
        headers: { "content-type": "application/json", "cache-control": "no-store" }
      });
    }
  }
};
