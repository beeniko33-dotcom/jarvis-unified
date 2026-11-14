# EURUSD market-data provider assurance review

**Review date:** 14 November 2026  
**Purpose:** Identify a technically credible, legally usable source for Jarvis's private, paper-only EURUSD research.  
**Decision:** **No provider approved yet. Keep the provenance gate BLOCKED_PROVENANCE and verified-day credit at zero.**

This is a public-document review, not vendor due diligence, legal advice, an independent audit, or a statement that any provider's claims have been verified. No account was created, no vendor was contacted, no terms were accepted, and no purchase was made.

## Decision summary

| Provider/product | What public material supports | Key unresolved assurance gap | Current disposition |
|---|---|---|---|
| LSEG Tick History – PCAP / FX Matching | Raw packet capture from the FX Matching venue, GPS nanosecond timestamps, venue-level source context, packet-level historical reconstruction | Public pages do not establish a cryptographic signature/key-verification protocol, continuous live-forward delivery, exact EURUSD entitlement, retention/audit contract or price | **Best technical diligence lead** for a venue-specific historical benchmark; not yet a forward-evidence provider |
| TickDataFeed FX Spot | 70+ spot FX pairs, bid/ask/mid, exchange timestamps, sequence-checked WSS, redundant capture claims, published checksums and a claim of signed files; public FX + Crypto plan price | No public signature format, signed-object scope, public-key distribution/rotation, verifier spec, or independent audit/attestation; source venue/liquidity composition and EURUSD sample still need confirmation | **Best published forward-stream candidate**, but cannot pass the current provenance gate yet |
| dxFeed Forex Spot | Public materials list Forex/Spot and Bid/Ask, direct-feed capture, historical tick extraction, market replay, and an on-demand tick-data audit endpoint | No public per-message signature or equivalent contractually auditable provenance specification found; exact EURUSD feed/source, forward availability, audit retention and pricing need written confirmation | **Secondary diligence lead**; audit endpoint is promising but not enough by itself |

## 1. TickDataFeed — FX Spot

### Publicly documented
- Vendor coverage page describes aggregated interbank spot FX across majors, minors and exotics, with 70+ pairs and bid/ask at tick level, plus mid and aggregated liquidity. It claims coverage since 2016. [Coverage](https://www.tickdatafeed.com/coverage.php)
- Vendor describes redundant dual-gateway capture, exchange-side timestamps, sequence checking with gap re-request/reconciliation, deterministic byte-identical replays and published checksums. The same page describes delivery of signed files and a sequence-checked live WebSocket stream. [Product overview](https://www.tickdatafeed.com/)
- Public price page lists the **FX + Crypto** plan at **₹20,000 per month**, billed monthly, GST as applicable, purchased through sales. Forex is included. It says sample files can be requested before purchase. [Pricing](https://www.tickdatafeed.com/pricing.php)
- Terms updated 10 November 2026 permit internal market-microstructure research, backtesting, and forward testing against live/delayed data when no orders are transmitted. They prohibit live-order use and making data available to third parties, including third-party paper/simulated trading products. Seat/environment limits are set by the order. [Terms](https://www.tickdatafeed.com/terms.php)

### Assurance assessment
The public claims are unusually specific about sequence continuity, exchange timestamps, reproducible checksums and signed files. However, a checksum is not a digital signature, and the public pages do not document enough to implement an independent signature verifier.

Before any evidence credit, obtain written answers and a sample:
1. Is the file signature cryptographic (for example Ed25519 or ECDSA), or is “signed” a vendor watermark/checksum?
2. What exact bytes are signed: raw venue payload, normalized file, manifest, or a container? Is the signature detached?
3. Provide the signature format, canonicalization rules, public-key fingerprints, key-distribution channel, rotation/revocation procedure and historical key archive.
4. Does the live WSS stream carry signed messages or signed sequence checkpoints? If not, what contractually auditable mechanism binds live events to the signed archive?
5. Provide a real EURUSD sample showing provider/venue identity, symbol mapping, bid, ask, event timestamp, receive timestamp, sequence/event ID, raw payload, manifest and signature/checksum.
6. Identify the underlying liquidity venues/contributors and whether the feed is a composite, broker stream or venue-specific source. Define what “aggregated interbank” means operationally.
7. Confirm whether the one-user private Jarvis research workflow is covered by the proposed order and whether local retention of raw payloads and audit artifacts is permitted.

**Cost:** Publicly listed at ₹20,000/month for FX + Crypto, plus applicable GST. No subscription is authorized. A sample and full licence/order terms should be reviewed first.

## 2. dxFeed — Forex Spot

### Publicly documented
- dxFeed's historical services page lists Forex and Spot coverage and data types including Bid/Ask, Last Sale, Time and Sales and order-book data. It describes direct feed capture and historical tick-level services. [Historical Data Services](https://dxfeed.com/data-services/historical-data-services/)
- dxFeed documents REST tick extraction and an on-demand tick-data audit web service that preserves event order and is intended primarily for trade-audit purposes. The public documentation says the audit service currently provides access to only one month of data on all symbols, subject to configurable limitations. [Historical Data Access](https://kb.dxfeed.com/en/data-services/historical-services/historical-data-access.html)
- The vendor describes real-time/delayed normalized feeds sourced from exchanges and other financial data sources. [Real-time and delayed data](https://dxfeed.com/data-services/real-time-and-delayed-data-service/)

### Assurance assessment
The ordered audit extraction is useful for reconstructing a recent period, and the published coverage includes spot FX bid/ask. But the public material reviewed does not establish cryptographic signatures, key custody, authenticated per-message source binding, or a contractual audit attestation for EURUSD spot. An audit API is not automatically a provenance verifier.

Questions to obtain in writing:
1. Is EURUSD specifically available as spot FX (not a CFD, future or synthetic index)? Which liquidity sources/venues contribute?
2. Are bid and ask independently sourced, with original event IDs, sequence numbers and provider timestamps?
3. Does the one-month audit API reproduce the exact original event stream or a normalized/reconstructed view? What is omitted?
4. Can dxFeed provide signed export manifests, immutable event IDs, sequence continuity proofs, or a contractual attestation binding payload to source, instrument, event time and price?
5. Can the real-time feed and audit export be cryptographically reconciled?
6. What are the retention, raw-payload storage, internal research-use, trial and pricing terms?

**Cost:** No public price sufficient for this use case was confirmed. Request a quote and trial scope. No account or subscription is authorized.

## 3. LSEG Tick History – PCAP / FX Matching

### Publicly documented
- LSEG describes Tick History – PCAP as packet-level historical data captured at source/data-centre level, with lossless capture, redundant capture processes, GPS nanosecond timestamps, and raw PCAP or normalized Parquet/CSV delivery. [Tick History – PCAP](https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history/tick-history-pcap)
- LSEG's FX-specific article states that the PCAP FX content is from **FX Matching**, its spot and forwards matching engine. It describes nanosecond timestamped data and says FX Matching was the only venue contributing PCAP data for FX price construction at the time of that article. It describes more than 70 currency pairs on the venue. [FX Matching PCAP overview](https://www.lseg.com/en/insights/fx/revolutionising-fx-price-transparency-with-tick-history-pcap)
- LSEG documents REST API access for Tick History clients, and offers a free-trial request path; API access itself is not a free data entitlement. [Tick History REST API](https://developers.lseg.com/en/api-catalog/refinitiv-tick-history/refinitiv-tick-history-rth-rest-api)
- Public pages do not show a price for the required EURUSD PCAP or live feed entitlement.

### Assurance assessment
This is the strongest public technical lead for a venue-specific historical reference because the product is packet capture from the FX Matching venue, with high-precision timestamps and preserved packet structure. It is not a representation of the entire OTC spot FX market; one venue's feed must be labelled as such. The public materials reviewed do not establish a cryptographic signature protocol or a live-forward PCAP stream for Jarvis. Historical PCAP alone cannot start a forward evidence clock.

Questions to obtain in writing:
1. Confirm EURUSD spot coverage in FX Matching PCAP, including bid/ask/order-book message types, venue identifiers and exact symbol mapping.
2. Confirm whether live-forward raw packet capture is available for the same venue, or whether the product is historical/T+1 only.
3. Provide PCAP integrity mechanisms: signed manifests, hashes, capture sequence continuity, GPS clock calibration records, key custody and audit reports.
4. Can the vendor provide a contractual attestation for the capture chain from venue feed handler through file delivery, including corrections, gaps and reissues?
5. Confirm source capture points, redundant A/B lines, arbitration logic and any lossy/normalization steps.
6. Confirm internal research rights, retention, raw-packet storage, use in a private paper-only prototype, trial availability, and full monthly/minimum contract cost.

**Cost:** Not publicly confirmed for the requested entitlement. Requires a sales quote. No purchase or terms acceptance is authorized.

## 4. Minimum acceptance test for any provider

A provider cannot receive evidence credit based on marketing language, TLS alone, checksums alone, or a successful parser. Before enabling a verifier, require:

- An exact instrument definition: EURUSD spot, source/venue/contributor, bid/ask semantics and precision.
- Original raw payload and immutable provider event ID/sequence, plus provider event time and local receive time.
- A cryptographic signature or independently auditable contractual attestation that binds the exact payload and relevant metadata.
- Published signature algorithm, canonicalization, key fingerprints, trusted key-distribution process, key rotation and revocation.
- Negative tests for invalid signature, modified price, wrong symbol, stale/future timestamp, replay, duplicate, sequence gap, key rollover and tampered manifest.
- A reproducible historical re-download or audit extract that matches the retained source hashes and correction/version policy.
- Written licence permission for internal single-owner research, storage and forward testing; no live orders and no third-party distribution.
- Independent review of verifier implementation and threat model before any change to the current evidence gate.

## Recommendation

Do **not** approve a provider or enable evidence credit yet.

1. Request a no-obligation EURUSD sample and technical assurance pack from TickDataFeed. It is the clearest published candidate for an ongoing forward stream and its monthly price is public, but the signature/key model must be demonstrated.
2. In parallel, request an FX Matching PCAP sample and a written live-versus-historical entitlement statement from LSEG. Treat it as a venue-specific historical audit benchmark unless LSEG confirms a suitable live-forward product.
3. Request dxFeed's EURUSD spot symbol/source specification and a sample onDemand audit extract, plus written confirmation of how the audit endpoint binds original event identity and payload.

No vendor has passed. Keep Deriv and Biquote records as unverified candidates, keep BLOCKED_PROVENANCE unchanged, and do not start the Level 3 evidence clock. This review does not authorize contacting vendors, accepting terms, opening accounts, or spending money.
