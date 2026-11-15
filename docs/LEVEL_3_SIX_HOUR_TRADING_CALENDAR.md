# Level 3 two-hour trading calendar

**Status: implementation proposal; not a certification or evidence-credit approval.**

The calendar uses a fixed **07:00-09:00 UTC** window on Monday-Friday. This is a
two-hour London-morning collection window, not a claim that the FX market trades only
two hours. Both hourly buckets must contain a fresh observation. One tick in a bucket
is sufficient only for bucket presence; it does not prove continuous feed uptime or
quote quality, and provider provenance remains a separate gate.

- Daily collection window: 07:00 through 08:59:59 UTC.
- Coverage: both hourly buckets (100% of the selected window).
- Streak: 30 consecutive expected trading days, not 30 calendar days.
- Weekends: neutral.
- Holidays: neutral only when explicitly added to the versioned calendar before the run.
- Unknown weekday closures and missing hourly buckets: break the streak.
- Calendar version and SHA-256 are bound into the evidence-store configuration. Changing
  the calendar requires a new database and a fresh validation run.
- The shortened window reduces daily collection time; it does not reduce the 30-trading-day
  requirement, compress elapsed time, or authorize live use.

The current Deriv and Biquote collectors mark every observation unverified. Consequently,
this calendar can report candidate coverage but cannot create verified-day credit or pass
the Level 3 provenance gate. The second-feed comparison remains a separate compensating
control and does not turn either feed into signed provenance.
