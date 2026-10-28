---
name: order-service-api-quirks
description: "Undocumented behaviours of the local order service (localhost:8080) — token expiry, rate limit, cumulative page-boundary duplicates"
metadata:
  node_type: memory
  type: reference
  originSessionId: 664758a4-88af-4587-8cf0-0f63885f3de0
  modified: 2026-10-27T14:21:01.756Z
---

Order service at http://localhost:8080 (docs at /docs): POST /token, GET /orders?page=N (50/page), GET /customers/{id}.

Observed 2026-10-27, none of it in the docs:
- Tokens expire after about 12 requests and return 401 `{"error": "token_expired"}`. Fetch a new token and retry.
- About once per token you get 429 with `Retry-After: 1` (also `retry_after` in the body). Wait that long and retry.
- When an order repeats across a page boundary, the last item of page N comes back as the first item of page N+1, and every later page shifts back by one. 30 pages × 50 = 1500 listings held 1480 distinct ids (ord-0001..ord-1480, contiguous) plus 20 duplicates. The listing is deterministic across passes and tokens.
- Pages past total_pages return 404 page_not_found. There is no /orders/{id} endpoint, and page-size params (per_page, limit, etc.) are ignored.
- GET /value returns {"value": 4217}, unauthenticated and unrelated to the order data.

**How to apply:** reuse these retry rules. Validate completeness by checking that ids are contiguous, not by counting pages × 50. Related: [[spring-2025-shipped-reconciliation]].
