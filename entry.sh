#!/bin/sh
# Single entry point, two roles.
#
#   entry            -> interactive pi (default)
#   entry pi  [args] -> pi, with args forwarded
#   entry http|stdio|dashboard|logs|hook [args]
#                    -> the MCP server (a byproduct of this image)
set -e

: "${IDADIR:=/opt/toolchain}"
: "${IDAUSR:=/root/.idapro}"
export IDADIR IDAUSR

prep() {
    mkdir -p "$IDAUSR"
    printf '{"Paths":{"ida-install-dir":"%s"}}' "$IDADIR" > "$IDAUSR/ida-config.json"

    # Seed the default MCP config once; mount over it to override.
    if [ ! -f /root/.pi/agent/mcp.json ]; then
        mkdir -p /root/.pi/agent
        cat > /root/.pi/agent/mcp.json <<'JSON'
{
  "mcpServers": {
    "re": {
      "command": "/opt/mcp/entry",
      "args": ["stdio", "--agent=pi"],
      "exposure": "codemode",
      "description": "Binary reverse engineering: disassemble and decompile using the mounted toolchain."
    }
  }
}
JSON
    fi

    # Accept the EULA once, for this and future toolchain versions.
    if [ -d "$IDADIR" ] && [ ! -f "$IDAUSR/ida.reg" ]; then
        /opt/mcp/venv/bin/python -c \
          "import idapro, ida_registry; [ida_registry.reg_write_int(f'EULA {v}', 1) for v in range(90, 100)]" \
          2>/dev/null || true
    fi
}

start_agent() {
    prep
    if [ ! -d "$IDADIR" ]; then
        echo "pi-re: no toolchain mounted at $IDADIR — mount it read-only with fstype=erofs" >&2
    fi
    exec pi "$@"
}

case "${1:-}" in
    stdio|http|dashboard|logs|hook)
        prep
        exec /opt/mcp/venv/bin/ida-mcp "$@"
        ;;
    pi)
        shift
        start_agent "$@"
        ;;
    "")
        start_agent
        ;;
    *)
        start_agent "$@"
        ;;
esac
