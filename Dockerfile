# syntax=docker/dockerfile:1
# Pi with a reverse-engineering MCP server built in.
#
# The toolchain is NOT in this image: mount it read-only at /opt/toolchain
# (an erofs image, for example) and pi can disassemble and decompile right away.
#
# The MCP server is a byproduct: the same image also serves other MCP clients
# over stdio or HTTP — see the README.
ARG PI_VERSION=latest
FROM ghcr.io/skiyer/pi-docker:${PI_VERSION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && UV_PYTHON_INSTALL_DIR=/opt/mcp/py UV_PYTHON_PREFERENCE=only-managed \
       uv venv --python 3.12 /opt/mcp/venv \
    && UV_PYTHON_INSTALL_DIR=/opt/mcp/py \
       uv pip install --python /opt/mcp/venv/bin/python --no-cache ida-mcp \
    && rm -rf /root/.cache

COPY entry.sh /opt/mcp/entry
RUN chmod +x /opt/mcp/entry

ENV IDADIR=/opt/toolchain \
    IDAUSR=/root/.idapro \
    IDA_MCP_STATE_DIR=/root/.idapro/mcp

WORKDIR /workspace
# No default CMD: with no arguments this starts an interactive pi session.
ENTRYPOINT ["/opt/mcp/entry"]
