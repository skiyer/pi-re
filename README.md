# pi-re

[Pi](https://pi.dev) coding agent with the MCP reverse-engineering server **built in**,
ready to use as soon as a toolchain image is mounted.

Nothing else to configure: the image ships the MCP server, a default `mcp.json`,
and the startup step that prepares the user directory and accepts the EULA on
first launch.

> The toolchain itself is **not** in this image. Mount it read-only and pi can
> disassemble and decompile immediately.

## Run

```bash
msb run ghcr.io/skiyer/pi-re:latest --name pi-re -it \
  --mount-disk ~/images/toolchain-arm64.erofs:/opt/toolchain:ro,fstype=erofs \
  --mount-dir  ~/work:/workspace
```

Then just ask:

```
反编译 /workspace/sample.bin，说明它做什么
```

That is the whole setup. Drop the extra mounts and it still runs — you only lose
the analysis tools.

## Mounts

| Guest path | Mode | Purpose |
|---|---|---|
| `/opt/toolchain` (`$IDADIR`) | **ro** | Toolchain image. Architecture must match the sandbox. |
| `/workspace` | rw | Your code / samples. Databases are written next to the sample. |
| `/root/.idapro` | rw | Optional: persist the user directory across runs. |
| `/root/.pi/agent` | rw | Optional: your own pi config and credentials. |

The image architecture and the toolchain architecture must match
(`amd64` ↔ `x64linux`, `arm64` ↔ `armlinux`).

## What is inside

| | |
|---|---|
| agent | `pi` (from [`pi-docker`](https://github.com/skiyer/pi-docker)) |
| MCP server | [`ida-mcp`](https://pypi.org/project/ida-mcp/) in a private venv under `/opt/mcp` |
| python | relocatable CPython 3.12 (uv-managed) |
| default `mcp.json` | `/root/.pi/agent/mcp.json`, written on first start |

`entry.sh` serves both roles: as the container entry point it prepares the
environment and runs `pi`; as the command pi spawns for the MCP server it runs in
stdio mode.

## Configuration

Override the default MCP config by mounting your own file:

```bash
--mount-dir ~/.pi/mcp.json:/root/.pi/agent/mcp.json:ro
```

Default:

```json
{
  "mcpServers": {
    "re": {
      "command": "/opt/mcp/entry",
      "args": ["stdio", "--agent=pi"],
      "exposure": "codemode"
    }
  }
}
```

Environment: `IDADIR` (default `/opt/toolchain`), `IDAUSR` (default
`/root/.idapro`), `IDA_MCP_STATE_DIR`.

## Where the toolchain comes from

Build it from your own installation and keep it out of the image — see
`re-toolchain-images`. Typical formats:

```bash
mkfs.erofs -zlz4hc -C65536 toolchain-arm64.erofs /path/to/install-tree
```

erofs is the portable choice: compressed, read-only by design, and accepted by
every sandbox backend (`fstype=erofs`).

## Build locally

```bash
docker build -t pi-re:local .
docker run --rm pi-re:local --version
```

CI builds `linux/amd64` and `linux/arm64` on push, on tags, weekly (to pick up
new MCP server releases), and on demand.

## License

MIT — see [LICENSE](LICENSE). This covers this repository only; the toolchain you
mount is governed by its own license.
