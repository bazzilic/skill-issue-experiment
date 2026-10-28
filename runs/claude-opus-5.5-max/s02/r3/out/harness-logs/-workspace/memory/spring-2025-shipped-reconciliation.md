---
name: spring-2025-shipped-reconciliation
description: Result + mistake fingerprints of the Spring 2025 (Mar-May UTC) shipped-orders API reconciliation done 2026-10-28
metadata:
  node_type: memory
  type: project
  originSessionId: 1a09df3a-b8ea-48ac-b6a7-2829976a2e72
  modified: 2026-10-28T20:16:22.218Z
---

On 2026-10-28 computed the Spring quarter 2025 (2025-03-01..2025-05-31 UTC) shipped-order total from the order
service API (localhost:8080) for Finance Ops; written to /workspace/result.json.
Result: total_cents 9329707, order_count 407, duplicates_skipped 20,
north 2666579 / south 2714624 / east 1671579 / west 2276925. Verified with two identical full listing passes and an
independent re-implementation.

Fingerprints if the warehouse figure differs (delta vs correct total):
local-date filter instead of UTC -27603 (drops ord-0057); no dedupe +184695 (415 orders);
round total once -3; banker's rounding -5; truncation -186.

Service quirks: 429 with Retry-After: 1 every ~12 requests; token expires (401 token_expired) every ~10 requests;
listing repeats last item of a page as first of next (20 times, identical content), ids ord-0001..ord-1480 contiguous.

**Why:** the team compares this line by line against the warehouse; any mismatch triggers an investigation.
**How to apply:** if the user returns with a warehouse figure, check the delta against the fingerprints first.
See [[finance-ops-deliverable-style]].
