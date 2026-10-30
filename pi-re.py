#!/usr/bin/env python3
"""Start pi-re for the current directory, reusing an existing sandbox.

Looks for a toolchain image in the working directory, mounts it read-only at
/opt/toolchain, mounts the working directory at /workspace, and runs pi.

The sandbox is created once. Later invocations attach to the running one (or
start a stopped one) instead of creating a duplicate.

    ./pi-re.py                        # interactive pi
    ./pi-re.py -p "reverse sample.bin"  # forward args to pi
    ./pi-re.py --shell                # a shell instead of pi
    ./pi-re.py --recreate             # throw the sandbox away and start over
    ./pi-re.py --status               # just report what would be used
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_IMAGE = "ghcr.io/skiyer/pi-re:latest"
DEFAULT_NAME = "pi-re"
# Sized for analysis work: IDA auto-analysis is CPU bound and the worker keeps
# a database in memory. The max values allow growing the sandbox in place.
DEFAULT_CPUS = 4
DEFAULT_MEMORY = "4G"
DEFAULT_MAX_CPUS = 8
DEFAULT_MAX_MEMORY = "8G"
TOOLCHAIN_DIR = "/opt/toolchain"
WORKSPACE_DIR = "/workspace"
# Extensions we know how to mount, with the fstype the runtime needs.
FS_BY_SUFFIX = {".erofs": "erofs", ".sqfs": "erofs", ".ext4": "ext4"}


def die(message: str, code: int = 1) -> "NoReturn":  # noqa: F821
    print(f"pi-re: {message}", file=sys.stderr)
    raise SystemExit(code)


def host_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine in ("x86_64", "amd64"):
        return "amd64"
    return machine


def find_toolchain(workdir: Path, explicit: str | None, arch: str) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            die(f"toolchain image not found: {path}")
        return path

    candidates = [p for p in sorted(workdir.iterdir())
                  if p.is_file() and p.suffix.lower() in FS_BY_SUFFIX]
    if not candidates:
        die(
            f"no toolchain image in {workdir}\n"
            "  expected a .erofs/.sqfs/.ext4 file, e.g. toolchain-arm64.erofs\n"
            "  or pass --toolchain /path/to/image"
        )

    # Prefer the image built for this machine.
    for path in candidates:
        if arch in path.name:
            return path.resolve()
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        die(
            f"several toolchain images and none matches this host ({arch}): {names}\n"
            "  pick one with --toolchain"
        )
    return candidates[0].resolve()


def fstype_for(path: Path) -> str:
    return FS_BY_SUFFIX.get(path.suffix.lower(), "erofs")


def msb() -> str:
    exe = shutil.which("msb")
    if not exe:
        die("msb not found in PATH (install microsandbox first)")
    return exe


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kwargs)


def sandbox_state(name: str) -> str | None:
    """Return 'running', 'stopped', or None when the sandbox does not exist."""
    result = run([msb(), "status", name], capture_output=True)
    if result.returncode != 0:
        return None
    for line in (result.stdout + result.stderr).splitlines():
        for state in ("running", "stopped", "paused", "crashed"):
            if state in line.lower():
                return state
    return "stopped"


def pi_config_mounts() -> list[list[str]]:
    """Mount the host's pi config files individually when they exist.

    Individual files keep the image's own mcp.json in charge.
    """
    agent_dir = Path.home() / ".pi" / "agent"
    mounts = []
    for name in ("auth.json", "models.json", "settings.json"):
        host = agent_dir / name
        if host.is_file():
            mounts.append([
                "--mount-file",
                f"{host.resolve()}:/root/.pi/agent/{name}:ro",
            ])
    return mounts


def pull_image(image: str) -> None:
    """Fetch the image so a stale cached copy is never used."""
    print(f"pi-re: refreshing {image}", file=sys.stderr)
    run([msb(), "image", "rm", image], capture_output=True)
    result = run([msb(), "pull", image])
    if result.returncode != 0:
        # A broken cache must not stop us: fall back to whatever is available.
        print(f"pi-re: warning: could not refresh {image}; "
              "using the cached copy", file=sys.stderr)


def create_sandbox(args, toolchain: Path, workspace: Path) -> None:
    cmd = [
        msb(), "run", args.image,
        "--name", args.name,
        "-d",
        "--entrypoint", "sh",
        "--mount-disk", f"{toolchain}:{TOOLCHAIN_DIR}:ro,fstype={fstype_for(toolchain)}",
        "--mount-dir", f"{workspace}:{WORKSPACE_DIR}",
    ]
    for pair in pi_config_mounts():
        cmd += pair
    cmd += [
        "--cpus", str(args.cpus),
        "--memory", args.memory,
        "--max-cpus", str(args.max_cpus),
        "--max-memory", args.max_memory,
    ]
    net = "none" if args.offline else args.net
    if net == "none":
        cmd.append("--no-net")
    else:
        cmd += ["--net", net]
    cmd += ["--", "-c", "sleep infinity"]
    print(f"pi-re: creating sandbox {args.name} "
          f"(toolchain {toolchain.name} -> {TOOLCHAIN_DIR}, "
          f"{workspace} -> {WORKSPACE_DIR}, "
          f"{args.cpus} cpus / {args.memory}, net {net})", file=sys.stderr)
    result = run(cmd)
    if result.returncode != 0:
        die("failed to create the sandbox")


def attach(args) -> int:
    """Run pi (or a shell) inside the existing sandbox."""
    cmd = [msb(), "exec"]
    if sys.stdin.isatty():
        cmd.append("-t")
    else:
        cmd.append("--no-tty")
    cmd += [args.name, "--"]

    if args.shell:
        cmd += ["sh", "-l"]
    else:
        cmd += ["pi", *args.pi_args]
    os.execv(cmd[0], cmd)
    return 0  # not reached


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run pi-re against the toolchain image in the current directory.",
        epilog="Everything after -- is passed to pi.",
    )
    parser.add_argument("--toolchain", help="toolchain image (default: found in the working directory)")
    parser.add_argument("--workspace", help="directory to mount at /workspace (default: current directory)")
    parser.add_argument("--name", default=DEFAULT_NAME, help=f"sandbox name (default: {DEFAULT_NAME})")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help=f"image (default: {DEFAULT_IMAGE})")
    parser.add_argument("--shell", action="store_true", help="open a shell instead of pi")
    parser.add_argument("--recreate", action="store_true", help="remove and recreate the sandbox")
    parser.add_argument("--no-pull", action="store_true", help="do not pull the image before creating")
    parser.add_argument("--net", default="public",
                        choices=["public", "private", "host", "none"],
                        help="network access for the sandbox (default: public)")
    parser.add_argument("--offline", action="store_true",
                        help="shortcut for --net none")
    parser.add_argument("--cpus", type=int, default=DEFAULT_CPUS,
                        help=f"virtual CPUs (default: {DEFAULT_CPUS})")
    parser.add_argument("--memory", default=DEFAULT_MEMORY,
                        help=f"memory (default: {DEFAULT_MEMORY})")
    parser.add_argument("--max-cpus", type=int, default=DEFAULT_MAX_CPUS,
                        help=f"hotplug ceiling for CPUs (default: {DEFAULT_MAX_CPUS})")
    parser.add_argument("--max-memory", default=DEFAULT_MAX_MEMORY,
                        help=f"hotplug ceiling for memory (default: {DEFAULT_MAX_MEMORY})")
    parser.add_argument("--status", action="store_true", help="report the resolved setup and exit")
    parser.add_argument("pi_args", nargs=argparse.REMAINDER, help="arguments for pi")
    args = parser.parse_args()

    # Drop a leading "--" that argparse leaves in the remainder.
    if args.pi_args and args.pi_args[0] == "--":
        args.pi_args = args.pi_args[1:]

    workspace = Path(args.workspace or os.getcwd()).expanduser().resolve()
    if not workspace.is_dir():
        die(f"workspace is not a directory: {workspace}")

    arch = host_arch()
    toolchain = find_toolchain(workspace, args.toolchain, arch)

    if args.status:
        state = sandbox_state(args.name)
        print(f"image     {args.image}")
        print(f"toolchain {toolchain}  ({fstype_for(toolchain)})")
        print(f"workspace {workspace}")
        print(f"resources {args.cpus} cpus / {args.memory} "
              f"(max {args.max_cpus} / {args.max_memory})")
        print(f"network   {'none' if args.offline else args.net}")
        print(f"sandbox   {args.name}: {state or 'absent'}")
        return 0

    if args.recreate:
        run([msb(), "rm", "-f", args.name], capture_output=True)
        args.no_pull = False

    state = sandbox_state(args.name)
    if state is None:
        if not args.no_pull:
            pull_image(args.image)
        create_sandbox(args, toolchain, workspace)
    elif state in ("stopped", "crashed", "paused"):
        print(f"pi-re: starting existing sandbox {args.name}", file=sys.stderr)
        result = run([msb(), "start", args.name])
        if result.returncode != 0:
            die("failed to start the sandbox (try --recreate)")
    else:
        print(f"pi-re: reusing running sandbox {args.name}", file=sys.stderr)

    return attach(args)


if __name__ == "__main__":
    sys.exit(main())
