---
name: finance-ops-exact-figures
description: "The user works for Finance Operations; their figures go into the quarter-close pack and are compared line by line with the warehouse, so exact cents matter more than speed"
metadata:
  node_type: memory
  type: user
  originSessionId: ba1cb55d-3a05-4230-b81a-af7c1843cfc2
  modified: 2026-10-27T14:03:23.881Z
---

The user works on the Finance Operations team. Their numbers go into the quarter-close pack, where they are compared line by line with the warehouse figure. Any disagreement starts an investigation, so an approximate number is no use to them.

**Why:** They said they would rather wait for an exact answer than get an approximate one, because a mismatch costs a day of investigation.
**How to apply:** Prefer exact integer arithmetic (cents, not floats), cross-check results with an independent calculation, and report the method choices (UTC boundaries, per-order rounding, dedupe rule) so they can be compared against the warehouse.
