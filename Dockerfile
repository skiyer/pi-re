# syntax=docker/dockerfile:1
# Pi with a reverse-engineering MCP server built in.
#
# The toolchain is NOT in this image: mount it read-only at /opt/toolchain
# (an erofs image, for example) and pi can disassemble and decompile right away.
#
# The MCP server is a byproduct: the same image also serves other MCP clients
# over stdio or HTTP — see the README.
#
# Versioning: the image tag is a build date (CalVer); what is inside is recorded
# in labels and in /opt/mcp/VERSIONS.
ARG PI_VERSION=latest

FROM ghcr.io/skiyer/pi-docker:${PI_VERSION}

# Re-declared after FROM so they are usable below.
ARG PI_VERSION=latest
ARG MCP_VERSION=latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && UV_PYTHON_INSTALL_DIR=/opt/mcp/py UV_PYTHON_PREFERENCE=only-managed \
       uv venv --python 3.12 /opt/mcp/venv \
    && UV_PYTHON_INSTALL_DIR=/opt/mcp/py \
       uv pip install --python /opt/mcp/venv/bin/python --no-cache "ida-mcp==${MCP_VERSION}" \
    && rm -rf /root/.cache \
    && pi --version > /opt/mcp/VERSIONS.pi \
    && /opt/mcp/venv/bin/python -c "import importlib.metadata as m; print(m.version('ida-mcp'))" > /opt/mcp/VERSIONS.mcp

COPY entry.sh /opt/mcp/entry
RUN chmod +x /opt/mcp/entry

ARG BUILD_VERSION=dev
RUN printf '%s\n' "${BUILD_VERSION}" > /opt/mcp/VERSIONS \
    && printf 'pi %s\nida-mcp %s\n' "$(cat /opt/mcp/VERSIONS.pi)" "$(cat /opt/mcp/VERSIONS.mcp)"

LABEL org.opencontainers.image.title="pi-re" \
      org.opencontainers.image.description="Pi coding agent with a reverse-engineering MCP server built in" \
      org.opencontainers.image.source="https://github.com/skiyer/pi-re" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      io.skiyer.pi.version="${PI_VERSION}" \
      io.skiyer.mcp.version="${MCP_VERSION}" \
      io.skiyer.toolchain.min="9.4"

ENV IDADIR=/opt/toolchain \
    IDAUSR=/root/.idapro \
    IDA_MCP_STATE_DIR=/root/.idapro/mcp

WORKDIR /workspace
# No default CMD: with no arguments this starts an interactive pi session.
ENTRYPOINT ["/opt/mcp/entry"]
