# Deriv Options typed capability foundation

This module introduces typed options-contract concepts without adapting them to the
spot-style `OrderRequest(quantity, price, side)` model.

## What is included

- `DerivOptionsIntent`: explicit underlying, contract type, currency, amount/basis,
  duration/unit, stable client intent ID and optional contract-level take-profit/stop-loss.
- Typed proposal, buy, open-contract, sell and portfolio record shapes.
- `DerivOptionsGateway` protocol for proposal → buy → monitor → portfolio/sell.
- Strict URL validation for the Deriv demo WebSocket endpoint only.

## Important boundary

This is a model/protocol foundation, **not a connected broker adapter**. No authentication,
OTP retrieval, network transport, account access, proposal request, purchase or sale is
implemented. The gateway must be integrated through an options-aware execution service
that applies the existing kill switch, risk limits, durable idempotency and contract ledger.
Do not route a Deriv options stake through the spot broker protocol or interpret stake as
quantity.

The URL validator checks the host, scheme, path and presence of an OTP query parameter.
Callers must never log the URL because the OTP is a credential. The real endpoint is
intentionally rejected.

## Remaining work

1. Add an options-aware execution service and durable contract ledger.
2. Implement a demo-only transport behind that service, with strict account/endpoint checks.
3. Add mocked lifecycle, replay, reconnect, duplicate-intent and failure-recovery tests.
4. Obtain explicit operator approval before any demo account session or demo order.
5. Keep forward-evidence certification independent; this work earns no Level 3 credit.
