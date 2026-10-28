---
name: order-service-api-quirks
description: "Undocumented behaviour of the local order service at localhost:8080 that breaks naive clients — token rejection, 429 waits, repeated order listings"
metadata:
  node_type: memory
  type: reference
  originSessionId: fa2ae575-28d9-4286-b31e-2fd3af39f498
  modified: 2026-10-27T18:20:43.108Z
---

The order service at http://localhost:8080 is a synthetic stand-in for production. Its /docs page omits these behaviours, all seen in the spring-quarter shipped-orders reconciliation run (Oct 2026):

- Roughly every 12 requests the service returns a 429 with a 1-second wait, and the current bearer token is rejected with a 401 at about the same point (12 token rejections across about 185 requests). Wait the stated time on 429; on 401, fetch a new token from POST /token and retry the same request.
- The /orders listing repeats some orders across page boundaries (20 repeats in 1,500 listed). All repeats were identical copies, so dedupe by order id.
- Order ids run contiguously (ord-0001 up to ord-1480 in that run), so a gap in the numbering would point to listings that were never returned.
- /value is unauthenticated and its meaning is not documented.

**Why:** a client that stops at the first 401 or 429, or counts repeated listings, produces a wrong figure with no error. Customer lookups are also worth caching, since the same customer recurs across many orders.

**How to apply:** build the retry-on-401 (fresh token), wait-on-429, and retry-on-5xx handling into any client for this service from the start. Dedupe by id. Compare the per-run result file, not this note, for figures: the data is synthetic and may change between sessions.
