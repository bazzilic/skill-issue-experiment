---
name: order-service-api-quirks
description: "Behaviour of the local order service (localhost:8080) that its /docs page leaves out — token expiry, 429 Retry-After, page-boundary duplicates, placed_at offsets"
metadata:
  node_type: memory
  type: reference
  originSessionId: ba1cb55d-3a05-4230-b81a-af7c1843cfc2
  modified: 2026-10-27T14:03:21.066Z
---

Observed 2026-10-27 while pulling the full order listing and customers for the spring 2025 reconciliation. None of this is in /docs.

- Bearer tokens from POST /token expire after roughly a dozen authenticated requests. The next call returns 401; fetch a new token and repeat the same request.
- Rate limiting returns 429 with a `Retry-After` header in whole seconds (it was 1 throughout). Wait that long, plus a little margin, then retry.
- The /orders listing repeats the last item of each page as the first item of the next one. Over 30 pages of 50 that gave 20 repeats, all byte-identical copies. The distinct ids run unbroken from ord-0001 to ord-1480, so nothing is missing.
- placed_at carries five offset forms: Z, +09:00, +02:00, -02:00, -05:00, +05:30. Convert to UTC before any date filter.
- Customer lookups for the 117 customers on the spring qualifying set all returned 200. None were unknown.

**Why:** Each of these needs handling or the pull silently breaks: an unrefreshed token or an ignored 429 stops the run, and skipping dedupe overcounts.
**How to apply:** For any future pull from this service, build in token refresh on 401, honour Retry-After on 429, dedupe by order id, and convert offsets to UTC. See [[workspace-output-hygiene]] for where scratch scripts belong.
