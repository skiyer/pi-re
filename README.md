# pi-re

[Pi](https://pi.dev) coding agent with a reverse-engineering MCP server built in.
Mount a toolchain image and it works — no configuration, no second container.

> The toolchain itself is **not** in this image. Mount it read-only at
> `/opt/toolchain` and pi can disassemble and decompile immediately.

## Run

```bash
msb run ghcr.io/skiyer/pi-re:latest --name pi-re -t \
  --mount-disk ~/images/toolchain-arm64.erofs:/opt/toolchain:ro,fstype=erofs \
  --mount-dir  ~/work:/workspace \
  -- pi
```

Then just ask:

```
反编译 /workspace/sample.bin，说明它做什么
```

`-- pi` (or no arguments at all) starts an interactive session; anything after
`pi` is forwarded to it, for example `-- pi -p "reverse /workspace/sample.bin"`.

`-t` allocates a pseudo-terminal. There is no `-i`: unlike Docker, microsandbox
attaches stdin by default. Use `--no-tty` for non-interactive runs.

## Mounts

| Guest path | Mode | Purpose |
|---|---|---|
| `/opt/toolchain` (`$IDADIR`) | **ro** | Toolchain image; architecture must match the sandbox |
| `/workspace` | rw | Your code and samples; databases are written next to the sample |
| `/root/.idapro` | rw | Optional: persist the user directory between runs |
| `/root/.pi/agent` | rw | Optional: your own pi config, credentials and sessions |

## The MCP server is a byproduct

The same image serves any MCP client. Two extra roles:

```bash
# stdio, for a client that spawns it
msb run ghcr.io/skiyer/pi-re:latest --name mcp \
  --mount-disk ~/images/toolchain-arm64.erofs:/opt/toolchain:ro,fstype=erofs \
  --mount-dir  ~/work:/workspace --no-tty -- stdio --agent=my-client

# HTTP, shared by several agents
msb run ghcr.io/skiyer/pi-re:latest --name mcp -d \
  --mount-disk ~/images/toolchain-arm64.erofs:/opt/toolchain:ro,fstype=erofs \
  --mount-dir  ~/work:/workspace \
  -p 127.0.0.1:8737:8737 -- http --host 0.0.0.0 --port 8737
```

Endpoint: `http://127.0.0.1:8737/mcp`. One server process = one shared analysis
session; run a single instance and let agents connect to it rather than starting
one per agent. The HTTP transport has **no authentication** — keep it on loopback
or reach it through an SSH tunnel.

Point another client at it, for example:

```bash
pi mcp add re --url http://127.0.0.1:8737/mcp --exposure codemode
```

## Use your own pi config

Mount your models, credentials and settings so the container uses the same
providers as your host. Mount the individual files, so the image's own MCP
config stays in charge:

```bash
  --mount-file ~/.pi/agent/auth.json:/root/.pi/agent/auth.json:ro \
  --mount-file ~/.pi/agent/models.json:/root/.pi/agent/models.json:ro \
  --mount-file ~/.pi/agent/settings.json:/root/.pi/agent/settings.json:ro
```

| File | Contents |
|---|---|
| `auth.json` | provider credentials |
| `models.json` | custom providers and model definitions |
| `settings.json` | default provider/model, extensions, tool settings |

Mount the whole directory (`--mount-dir ~/.pi/agent:/root/.pi/agent`) instead if
you want sessions and caches to persist — then your own `mcp.json` wins and the
built-in one is not written.

## What is inside

| | |
|---|---|
| agent | `pi` (from [`pi-docker`](https://github.com/skiyer/pi-docker)) |
| MCP server (`re-mcp`) | in a relocatable venv at `/opt/mcp` |
| python | uv-managed CPython 3.12, no system dependency |
| default `mcp.json` | written on first start at `/root/.pi/agent/mcp.json` |

`entry.sh` is the only entry point: with no arguments (or `pi`) it prepares the
environment and runs pi; with `stdio`/`http`/… it runs the MCP server instead.

## Versioning

Releases are automatic — there is no manual version decision.

**The image tag is a build date (CalVer).** Each run derives the next tag from
the calendar, so a rebuild never overwrites a version you already pinned:

```
2026.10.30        first build that day
2026.10.30.1      a later build that day
latest            most recent build
```

**What is inside is recorded, not encoded in the tag.** Every image carries
labels and a `VERSIONS` file:

```bash
docker inspect ghcr.io/skiyer/pi-re:2026.10.30 --format '{{json .Config.Labels}}'
docker run --rm --entrypoint cat ghcr.io/skiyer/pi-re:2026.10.30 /opt/mcp/VERSIONS.pi
```

| Label | Example |
|---|---|
| `org.opencontainers.image.version` | `2026.10.30` |
| `io.skiyer.pi.version` | `1.4.0` |
| `io.skiyer.mcp.version` | `20261028.0.3` |
| `io.skiyer.toolchain.min` | `9.4` |

The build pins both inputs, so a tag is reproducible: the base is
`pi-docker:<pi version>` and the server package is pinned to `<mcp version>`.

**The toolchain is versioned independently and is orthogonal to the image:**

| Artifact | Version | Meaning |
|---|---|---|
| `pi-re:<calver>` | build date | this image (pi + MCP runtime) |
| `toolchain-*` | release tag, e.g. `toolchain-v2` | which toolchain ships inside |

```
pi-re:<anything>   works with any toolchain-vN whose architecture matches
```

so upgrading the toolchain never requires rebuilding or re-pulling the image:
download the new image file and mount it instead. See
[`re-toolchain-images`](https://github.com/skiyer/re-toolchain-images) for how
those are built.

## How upgrades arrive

The two upstream versions are pinned in plain files, which Dependabot watches:

| File | Pin |
|---|---|
| `package.json` | `@earendil-works/pi-coding-agent` |
| `requirements.txt` | `ida-mcp==<version>` |

Dependabot opens a PR when either moves; the PR is validated (both pins resolve,
the base image exists, the image builds and starts) and merged automatically.
The merge triggers the build, which publishes a new CalVer tag and a release
recording the component versions.

Nothing is rebuilt when no pin changed.

## Build locally

```bash
docker build --pull -t pi-re:local .
docker run --rm pi-re:local --version
```

`--pull` matters: the base is `pi-docker:latest`, and a stale local copy of that
tag will silently bake an old pi into this image.

CI builds `linux/amd64` and `linux/arm64` on push, on tags, weekly (to pick up new
MCP server releases), and on demand.

## License

MIT — see [LICENSE](LICENSE). This covers this repository only; the toolchain you
mount is governed by its own license.
