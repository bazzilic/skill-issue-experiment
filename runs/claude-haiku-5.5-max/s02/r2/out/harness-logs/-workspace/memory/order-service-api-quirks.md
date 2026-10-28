---
name: order-service-api-quirks
description: "Behaviours of the local OrderService API (localhost:8080) that /docs does not mention: short-lived tokens, 429 format, page-boundary duplicates, half-cent rounding ties."
metadata:
  node_type: memory
  type: reference
  originSessionId: 8ac4111c-1d9c-4983-85f8-05bde3996318
  modified: 2026-10-27T14:48:52.492Z
---

Observed during the spring quarter 2025 shipped-orders reconciliation (run on 2026-10-27):

- Tokens from POST /token expire within a few seconds. An expired one gets HTTP 401 with `{"error": "token_expired"}`. Fetch a new token on every 401 and repeat the same request.
- Rate limiting returns HTTP 429 with a `Retry-After: 1` header and body `{"error": "rate_limited", "retry_after": 1}`. It hit about every other request. Waiting the stated time and retrying the same request always succeeded.
- /orders returns 50 items per page. On about 20 of the 29 page boundaries, the last item of page N is repeated as the first item of page N+1. The repeats are identical copies. Ids run ord-0001 to ord-1480 with no gaps, so nothing is missing.
- /customers/{id} returned 200 for every customer on qualifying orders. No 404s came up.
- placed_at offsets seen: Z, +09:00, +02:00, -02:00, -05:00, +05:30. No timestamps lacked an offset.

**Why:** /docs is terse and does not mention these. Without handling them, a run fails early on 401s and 429s, or gets wrong numbers from the duplicates.

**How to apply:** Retry 401 (refresh token) and 429 (wait Retry-After) on every request, and keep fetching the same page after an error. De-duplicate by order id. Cache customer lookups. Keep the rounding rule literal: round each order's discounted amount half up. That matters for exact half-cent ties, of which there were 8 in this run. Rounding the discount first and subtracting it would have been 8 cents lower in total. If the warehouse differs by a few cents, check this first. See also [[finance-ops-exact-figures]].
