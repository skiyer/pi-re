# syntax=docker/dockerfile:1
# Pi coding agent with the MCP reverse-engineering server built in.
#
# The toolchain is NOT in this image: mount it read-only at /opt/toolchain
# (e.g. an erofs image) and everything works with no extra configuration.
FROM ghcr.io/skiyer/pi-docker:latest

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
ENTRYPOINT ["/opt/mcp/entry", "pi"]
CMD ["--help"]
