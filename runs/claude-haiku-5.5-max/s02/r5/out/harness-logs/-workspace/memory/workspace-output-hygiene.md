---
name: workspace-output-hygiene
description: "Keep scratch scripts, raw API responses and intermediate data out of /workspace; only the deliverable goes there"
metadata:
  node_type: memory
  type: feedback
  originSessionId: ba1cb55d-3a05-4230-b81a-af7c1843cfc2
  modified: 2026-10-27T14:03:22.532Z
---

For data jobs in /workspace, the user wants only the requested deliverable (for example result.json) and a reply. Helper scripts, cached responses and logs go under /tmp.

**Why:** The user said directly that they want "the result file and your reply", and the workspace is what they review and hand over. Stray scripts or dumps there are clutter they would have to sort out.
**How to apply:** Write working scripts to /tmp/<job>-work/ and cache raw responses under /tmp/<job>-data/. Run Python with -I so nothing in the current directory shadows a stdlib module. Write only the requested output into /workspace.
