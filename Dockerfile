# syntax=docker/dockerfile:1.8

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The published image is intentionally an offline simulation artifact. It does
# not contain qdbus or either provider CLI, and its entrypoint refuses every
# command that could inspect or control a host terminal.
ARG PYTHON_IMAGE=python:3.14-slim@sha256:c3e521df8b2b498a7a682e7e18676771cb80c6b75b8699af886b2d554ce40151
FROM ${PYTHON_IMAGE}

ARG VERSION
ARG REVISION=unknown
ARG CREATED=unknown

LABEL org.opencontainers.image.title="Agent While True safety simulator" \
      org.opencontainers.image.description="Offline safety simulations only; container terminal automation is unsupported" \
      org.opencontainers.image.source="https://github.com/marcelpetrick/AgentWhileTrue" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}"

ENV HOME=/home/agentwhiletrue \
    XDG_STATE_HOME=/home/agentwhiletrue/.local/state \
    XDG_CONFIG_HOME=/home/agentwhiletrue/.config \
    XDG_RUNTIME_DIR=/home/agentwhiletrue/.run \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 10001 agentwhiletrue \
 && useradd --uid 10001 --gid 10001 --create-home \
      --home-dir /home/agentwhiletrue agentwhiletrue \
 && install -d -o 10001 -g 10001 -m 0700 \
      /home/agentwhiletrue/.local/state \
      /home/agentwhiletrue/.config \
      /home/agentwhiletrue/.run

# VERSION is part of the path on purpose: a populated local dist/ directory
# cannot make Docker silently install an older wheel through a wildcard.
COPY dist/agent_while_true-${VERSION}-py3-none-any.whl /tmp/
RUN test -n "${VERSION}" \
 && python -m pip install --no-cache-dir --no-deps \
      "/tmp/agent_while_true-${VERSION}-py3-none-any.whl" \
 && python -c "import agent_while_true as package; assert package.__version__ == '${VERSION}'" \
 && rm "/tmp/agent_while_true-${VERSION}-py3-none-any.whl"

COPY --chmod=0755 scripts/container-entrypoint.sh /usr/local/bin/agent-while-true-container
COPY --chmod=0755 scripts/container-simulate.py /usr/local/bin/agent-while-true-container-cli

USER 10001:10001
ENTRYPOINT ["/usr/local/bin/agent-while-true-container"]
CMD []
