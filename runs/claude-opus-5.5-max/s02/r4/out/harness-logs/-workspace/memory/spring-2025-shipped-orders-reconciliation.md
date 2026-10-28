---
name: spring-2025-shipped-orders-reconciliation
description: "Finance Ops spring-quarter (Mar-May 2025 UTC) shipped-orders API figure, its rounding/date sensitivities, and order-service quirks"
metadata:
  node_type: memory
  type: project
  originSessionId: 25d6c262-e0a7-4f25-8118-5e1c570b7f71
  modified: 2026-10-27T15:04:06.863Z
---

On 2026-10-27, computed the API-side figure for the Finance Ops quarter-close pack from the local order service (http://localhost:8080). It is compared line by line against the warehouse figure. Result is in /workspace/result.json: total 9,329,707 cents, 407 shipped orders, 20 duplicate listings skipped. By region: north 2,666,579, south 2,714,624, east 1,671,579, west 2,276,925.

Sensitivities to check first if the warehouse disagrees:
- Rounding: 8 qualifying orders land exactly on a half cent. Per-order half-up gives 9,329,707. Rounding the total once gives 9,329,704 (-3). Banker's rounding gives 9,329,702 (-5).
- Date range: only ord-0057 (2025-02-28T23:10:03-02:00, which is 01:10 UTC on 1 March) changes when the range is applied in UTC instead of on the local date.

Service quirks:
- Tokens expire after about 12 requests (401 {"error":"token_expired"}).
- Rate limiting returns 429 with Retry-After: 1.
- Duplicates are deterministic: on 20 page boundaries the last order of a page is repeated, as an identical copy, as the first order of the next page.
- Order ids run ord-0001 to ord-1480 with no gaps. There are 120 customers and none return 404.

Scratch scripts and raw data were left in /tmp/recon_work, which may not persist.

**Why:** a follow-up asking why the warehouse figure differs is likely. The user values exact answers over fast ones.
**How to apply:** start any discrepancy investigation from the sensitivities above, and keep replies short with no write-up of the service (see [[user-prefers-concise-exact-deliverables]]).
