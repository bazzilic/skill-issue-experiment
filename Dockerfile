FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Harness versions are pinned.
RUN npm install -g @anthropic-ai/claude-code@2.1.308 @openai/codex@0.164.0

COPY server.py /opt/skill-issue/server.py
RUN mkdir /session /out /workspace && chown node:node /session /out /workspace

ENV DISABLE_AUTOUPDATER=1
USER node
WORKDIR /workspace
