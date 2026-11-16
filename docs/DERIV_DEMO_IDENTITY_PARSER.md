# Deriv demo identity claim parser

The offline Stage A parser in `brokers/deriv/identity.py` checks the documented
authorize-response account fields: selected `loginid`, top-level `is_virtual`,
and the matching `account_list` entry's `account_type`, `is_virtual`,
`is_disabled`, `currency`, and `landing_company_name`.

It fails closed for missing, malformed, duplicate, disabled, non-trading, or
non-virtual selected accounts. The returned account fingerprint is a local
SHA-256 pseudonym; it is not a provider-issued identifier or authentication proof.

**Critical limitation:** this is a parser for provider-shaped data, not a live
Deriv connection. A fabricated response can pass unit tests. The returned status
is always `PROVIDER_CLAIMED_DEMO_UNVERIFIED`; provider authenticity remains
false and evidence eligibility remains false. No credentials, network calls,
OTP handling, order capability, or runtime wiring are added. The main runtime
remains paper-only.

The field shape is based on Deriv's published authorization response example:
https://api.deriv.com/docs/core-concepts/authorization-authentication/
