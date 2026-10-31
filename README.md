# pi-re

[Pi](https://pi.dev) coding agent with a reverse-engineering MCP server built in.
Mount a toolchain image and it works — no configuration, no second container.

> The toolchain itself is **not** in this image. Mount it read-only at
> `/opt/toolchain` and pi can disassemble and decompile immediately.

## Quick start

Drop a toolchain image into a project directory and run the launcher:

```bash
cd ~/work/my-target
cp ~/images/toolchain-9.5-arm64.erofs .
./pi-re.py
```

`pi-re.py` finds the toolchain image in the working directory, mounts it read-only
at `/opt/toolchain`, mounts the directory at `/workspace`, and starts pi. Run it
again and it attaches to the existing sandbox instead of creating another one.

Toolchain files are named `toolchain-<version>-<arch>.erofs`. When several are
present the newest version for this machine's architecture is used, and the
choice is printed:

```bash
pi-re: using toolchain-9.5-arm64.erofs (of toolchain-9.4-arm64.erofs, toolchain-9.5-arm64.erofs)
```

Then just ask:

```
反编译 /workspace/sample.bin，说明它做什么
```

## Launcher options

```bash
./pi-re.py                          # interactive pi
./pi-re.py -p "reverse sample.bin"  # args go to pi
./pi-re.py --shell                  # a shell instead of pi
./pi-re.py --status                 # show what would be mounted/used
./pi-re.py --recreate               # throw the sandbox away and start fresh
./pi-re.py --toolchain ~/images/toolchain-9.4-arm64.erofs
./pi-re.py --workspace ~/other-dir
./pi-re.py --name my-target         # one sandbox per project
```

### Resources

The launcher sizes the sandbox for analysis work, not for a demo:

| | default | hotplug ceiling |
|---|---|---|
| CPUs | `4` | `8` |
| memory | `4G` | `8G` |

Override per run:

```bash
./pi-re.py --cpus 8 --memory 8G
./pi-re.py --cpus 2 --memory 2G --max-memory 4G
```

Resource settings are fixed when the sandbox is created; changing them requires
`--recreate` (or `msb modify` on a running sandbox). `--status` shows what the
next creation would use.

### Network access

Off by default? No — pi needs to reach your model provider, so the default is
`--net public`. Restrict it when you analyse something sensitive and drive the
model elsewhere:

```bash
./pi-re.py --net private            # private networks only
./pi-re.py --net host               # host network
./pi-re.py --offline                # no network at all (== --net none)
```

Network policy is fixed when the sandbox is created. Changing it requires
`--recreate`; the launcher prints the policy it used.

### Multiple projects

The sandbox name is derived from the workspace path:

```
pi-re-<directory>-<hash of the full path>
```

so two directories that happen to share a name still get separate sandboxes, and
the same project always reuses its own:

```bash
cd ~/work/proj-a && ./pi-re.py     # pi-re-proj-a-1a2b3c
cd ~/work/proj-b && ./pi-re.py     # pi-re-proj-b-4d5e6f
```

Override it with `--name` when you want a fixed, readable name:

```bash
./pi-re.py --name proj-a
```

## Without the launcher

The image works with plain `msb`:

```bash
msb run ghcr.io/skiyer/pi-re:latest --name pi-re -t \
  --mount-disk ~/images/toolchain-arm64.erofs:/opt/toolchain:ro,fstype=erofs \
  --mount-dir  ~/work:/workspace \
  -- pi
```

`-t` allocates a pseudo-terminal; there is no `-i` (unlike Docker, microsandbox
attaches stdin by default). Use `--no-tty` for non-interactive runs.

## Mounts

| Guest path | Mode | Purpose |
|---|---|---|
| `/opt/toolchain` (`$IDADIR`) | **ro** | Toolchain image; architecture must match the sandbox |
| `/workspace` | rw | Your code and samples; databases are written next to the sample |
| `/root/.idapro` | rw | Optional: persist the user directory between runs |
| `/root/.pi/agent` | rw | Optional: your own pi config, credentials and sessions |

## The MCP server is a byproduct

The same image serves any MCP client:

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

```bash
pi mcp add re --url http://127.0.0.1:8737/mcp --exposure codemode
```

## Use your own pi config

Mount your models, credentials and settings so the container uses the same
providers as your host. The launcher does this automatically, file by file:

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

## How upgrades arrive

The two upstream versions are pinned in plain files, which Dependabot watches:

| File | Pin | Ecosystem |
|---|---|---|
| `Dockerfile` | `FROM ghcr.io/skiyer/pi-docker:<version>` | docker |
| `requirements.txt` | `ida-mcp==<version>` | pip |

Dependabot opens a PR when either moves; the PR is validated (the base image is
already published, the server version exists, the image builds and starts) and
merged automatically. The merge triggers the build, which publishes a new CalVer
tag and a release recording the component versions.

The agent version is **not** resolved from npm here. It comes from the
`pi-docker` image tag, so this repository can never run ahead of
[`pi-docker`](https://github.com/skiyer/pi-docker): a PR bumping the base image
fails validation until that tag exists. Both repositories upgrade the same way —
a Dependabot PR that is merged once upstream has published.

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
labels and `VERSIONS*` files:

```bash
docker inspect ghcr.io/skiyer/pi-re:2026.10.30 --format '{{json .Config.Labels}}'
docker run --rm --entrypoint cat ghcr.io/skiyer/pi-re:2026.10.30 /opt/mcp/VERSIONS.base
```

| Label | Example |
|---|---|
| `org.opencontainers.image.version` | `2026.10.30` |
| `io.skiyer.pi.version` | `1.4.0` |
| `io.skiyer.mcp.version` | `20261028.0.3` |
| `io.skiyer.toolchain.min` | `9.4` |

Every build also creates a matching git tag and GitHub release whose notes list
the component versions of that build.

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

## Build locally

```bash
docker build --pull -t pi-re:local .
docker run --rm pi-re:local --version
```

`--pull` matters: the base is a pinned `pi-docker` tag, and a stale local copy of
it will silently bake an old pi into this image.

CI builds `linux/amd64` and `linux/arm64` whenever a pin changes, and on demand.

## License

MIT — see [LICENSE](LICENSE). This covers this repository only; the toolchain you
mount is governed by its own license.
