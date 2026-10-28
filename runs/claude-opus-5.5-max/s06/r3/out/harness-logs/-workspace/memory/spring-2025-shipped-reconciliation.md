---
name: spring-2025-shipped-reconciliation
description: "API-derived figure for Mar–May 2025 shipped orders (Finance Ops quarter-close), to be compared against the warehouse figure"
metadata:
  node_type: memory
  type: project
  originSessionId: 664758a4-88af-4587-8cf0-0f63885f3de0
  modified: 2026-10-27T14:20:57.042Z
---

On 2026-10-27 I computed, for Finance Ops, the spring-quarter (2025-03-01 to 2025-05-31 inclusive, UTC) total of status=="shipped" orders after per-customer discount (rounded half up per order), from the order service API at http://localhost:8080 (synthetic stand-in for production).

Result written to /workspace/result.json: total_cents 9329707, order_count 407, duplicates_skipped 20, by_region north 2666579, south 2714624, east 1671579, west 2276925. Verified by a second, independent implementation and a second listing pass.

Only one qualifying order (ord-0057, 2025-02-28T23:10:03-02:00) flips into range because of the UTC conversion; 8 orders hit an exact half cent.

**Why:** the figure goes into the quarter-close pack and will be compared line by line with the warehouse figure. Any mismatch starts an investigation, and the first check will be whether this figure was computed correctly.
**How to apply:** if asked about a mismatch, start from these numbers and the quirks in [[order-service-api-quirks]]. Raw pulls and scripts were in /tmp/recon_work, which may no longer exist. See also [[finance-ops-deliverable-preferences]].
