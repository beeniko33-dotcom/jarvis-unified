# Options-aware execution and contract ledger foundation

This module is a fail-closed orchestration foundation, not a live broker adapter.

## Boundaries
- The gateway is injected; construction and imports perform no network or account action.
- The policy defaults to kill switch engaged, operator disabled, demo account mode, and zero permitted stake/exposure.
- A buy intent is durably recorded before the gateway call. An ambiguous response is marked `buy_unknown` and must be reconciled; it cannot be retried under the same client intent ID.
- The ledger stores only an explicit allowlist of contract fields. Credentials, OTPs, tokens and arbitrary metadata are not accepted.
- No real endpoint, authentication flow, Deriv account connection, or broker order is implemented here.
- This foundation does not earn Level 3 forward-evidence credit.

## Remaining work before a demo adapter
1. Integrate the existing risk engine and reservation model through a reviewed options-specific risk interface.
2. Implement remote portfolio/open-contract reconciliation and crash recovery for pending/unknown buys.
3. Add settlement and early-sell transitions with idempotency and remote state verification.
4. Add a demo-only transport with strict endpoint and account-identity validation.
5. Run full repository tests and exact-head CI; conduct independent code review.
6. Obtain separate explicit operator approval before any demo connection or order.

Never convert an ambiguous timeout into a second buy request. Reconcile remote state first; fail closed if it cannot be established.
