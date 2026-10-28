---
name: finance-ops-exact-figures
description: "Finance Operations wants exact figures for the quarter-close pack, which is checked line by line against the warehouse. Approximate answers are not useful."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8ac4111c-1d9c-4983-85f8-05bde3996318
  modified: 2026-10-27T14:48:55.979Z
---

The user (Finance Operations) needs figures for the quarter-close pack. Those figures are compared line by line against the warehouse. An approximate result is no use: it either matches exactly or starts an investigation.

**Why:** A mismatch costs someone a day of checking, and the first thing they check is whether the API figure was computed correctly.

**How to apply:** Prefer a slower run that is verified over a fast estimate. Re-check results against the raw data by an independent route before reporting them. Write only the requested output file into the workspace, and keep scripts and raw responses in a scratch directory outside it. Report any rounding choice that moves the total by cents, and say which reading you took. See [[order-service-api-quirks]] for the service-side details.
