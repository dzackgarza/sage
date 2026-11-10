#!/usr/bin/env python3
"""Run the published research image on a host without a container runtime.

The environment these repositories write Sage against is the image
``ghcr.io/dzackgarza/sage``: this tree with CPython 3.14, GAP, Julia/Oscar,
Macaulay2, Singular and Lean.  A container image is a filesystem and a
process, so a host that cannot run Docker, chroot or PRoot can still use it:
this script fetches the image layer by layer from the registry, verifies every
digest, unpacks it into a cache directory, and runs commands inside that tree
with bubblewrap's unprivileged user namespaces.  There is no daemon, no root
and no ptrace.

    docker/sage-image.py fetch
    docker/sage-image.py run -- sage -c 'print(ZZ(2)**10)'
    docker/sage-image.py check

``fetch`` records the index, manifest, config and source revision it unpacked;
``--digest`` pins the image and makes the cache single-use, and ``info`` prints
what the cache holds.  ``run`` passes ``--`` and everything after it to the
image, with the current directory mounted at its own path so a checkout of a
consumer repository is visible at the path its tests expect.

bubblewrap must be installed (``apt install bubblewrap``, ``dnf install
bubblewrap``) and the kernel must allow unprivileged user namespaces; ``run``
names which of the two is missing.  Where neither is available, run the job in
the image on a CI runner (see ``.github/workflows/research-image-consumer.yml``)
or on a machine with a container runtime.  A distribution Sage is not this
environment, and import failures under one say nothing about the libraries in
the image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

REGISTRY = "https://ghcr.io"
IMAGE = "dzackgarza/sage"
REFERENCE = "develop"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "sage-image"
STAMP = "image.json"

ACCEPT_INDEX = "application/vnd.oci.image.index.v1+json"
ACCEPT_MANIFEST = "application/vnd.oci.image.manifest.v1+json"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def token(image: str) -> str:
    url = f"{REGISTRY}/token?scope=repository:{image}:pull&service=ghcr.io"
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)["token"]


def blob_request(credentials: str, image: str, path: str, accept: str) -> urllib.request.Request:
    return urllib.request.Request(
        f"{REGISTRY}/v2/{image}/{path}",
        headers={"Authorization": f"Bearer {credentials}", "Accept": accept},
    )


def read_json(credentials: str, image: str, path: str, accept: str) -> tuple[bytes, dict]:
    with urllib.request.urlopen(blob_request(credentials, image, path, accept), timeout=120) as response:
        body = response.read()
    return body, json.loads(body)


def resolve(credentials: str, image: str, reference: str) -> dict:
    """Return the linux/amd64 manifest and the digests that name it."""
    body, index = read_json(credentials, image, f"manifests/{reference}", ACCEPT_INDEX)
    index_digest = "sha256:" + hashlib.sha256(body).hexdigest()
    entry = next(
        manifest
        for manifest in index["manifests"]
        if manifest.get("platform", {}).get("os") == "linux"
        and manifest.get("platform", {}).get("architecture") == "amd64"
    )
    _, manifest = read_json(credentials, image, f"manifests/{entry['digest']}", ACCEPT_MANIFEST)
    return {
        "image": image,
        "reference": reference,
        "index": index_digest,
        "manifest": entry["digest"],
        "config": manifest["config"]["digest"],
        "layers": manifest["layers"],
    }


def stamp_path(cache: Path) -> Path:
    return cache / STAMP


def read_stamp(cache: Path) -> dict | None:
    try:
        return json.loads(stamp_path(cache).read_text())
    except FileNotFoundError:
        return None


def fetch_blob(credentials: str, image: str, digest: str, destination: Path) -> None:
    sha = hashlib.sha256()
    with urllib.request.urlopen(blob_request(credentials, image, f"blobs/{digest}", "*/*"), timeout=300) as response:
        with destination.open("wb") as handle:
            while chunk := response.read(1 << 22):
                sha.update(chunk)
                handle.write(chunk)
    if "sha256:" + sha.hexdigest() != digest:
        raise SystemExit(f"layer {digest} does not match its digest; the registry or the transfer is corrupt")


def clear(directory: Path) -> None:
    for entry in directory.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def apply_layer(blob: Path, root: Path) -> int:
    """Apply one OCI layer, resolving whiteouts; return the members skipped."""
    skipped = 0
    with tarfile.open(blob) as archive:
        for member in archive.getmembers():
            name = member.name
            base = os.path.basename(name)
            parent = root / os.path.dirname(name)
            if base == ".wh..wh..opq":
                if parent.is_dir():
                    clear(parent)
                continue
            if base.startswith(".wh."):
                target = parent / base[4:]
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
                continue
            if not (member.isreg() or member.isdir() or member.issym() or member.islnk()):
                continue
            try:
                archive.extract(member, root, filter="fully_trusted", set_attrs=True)
            except (PermissionError, OSError):
                # A path this user may not write, or an owner it may not set:
                # the content that matters to Sage is readable without it.
                skipped += 1
    return skipped


def unpack(cache: Path, image: str, reference: str, digest: str | None) -> dict:
    credentials = token(image)
    resolved = resolve(credentials, image, digest or reference)
    if digest and resolved["manifest"] != digest:
        raise SystemExit(f"{reference} resolves to {resolved['manifest']}, not the requested {digest}")
    previous = read_stamp(cache)
    root = cache / "rootfs"
    if previous and previous.get("manifest") == resolved["manifest"] and root.is_dir() and any(root.iterdir()):
        log(f"reusing {root} unpacked from {resolved['manifest']}")
        return previous

    _, config = read_json(credentials, image, f"blobs/{resolved['config']}", "*/*")
    resolved["revision"] = config.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision", "")
    # What the image declares for its own processes: JULIA_DEPOT_PATH, SAGE_BIN,
    # PATH and the rest. A container runtime applies these; so does this one.
    resolved["env"] = config.get("config", {}).get("Env", []) or []
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    log(f"{len(resolved['layers'])} layers, {sum(layer['size'] for layer in resolved['layers']) / 1e9:.2f} GB compressed")
    blob = cache / "layer.blob"
    skipped = 0
    for position, layer in enumerate(resolved["layers"], start=1):
        log(f"[{position}/{len(resolved['layers'])}] {layer['size'] / 1e6:.1f} MB {layer['digest'][:19]}")
        fetch_blob(credentials, image, layer["digest"], blob)
        skipped += apply_layer(blob, root)
        blob.unlink()
    if skipped:
        log(f"{skipped} files not writable by this user; the rest of the image is intact")
    record = {key: resolved[key] for key in ("image", "reference", "index", "manifest", "config", "revision", "env")}
    record["unpacked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stamp_path(cache).write_text(json.dumps(record, indent=2) + "\n")
    return record


def user_namespaces() -> str | None:
    """Return why unprivileged user namespaces are unavailable, if they are."""
    knob = Path("/proc/sys/kernel/unprivileged_userns_clone")
    if knob.exists() and knob.read_text().strip() == "0":
        return "/proc/sys/kernel/unprivileged_userns_clone is 0"
    # A failure here is the answer, not an error: the caller reports why the
    # namespace is unavailable.
    probe = subprocess.run(
        ["bwrap", "--unshare-user-try", "--ro-bind", "/", "/", "--", "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        reason = (probe.stderr or "bwrap cannot create a user namespace").strip().splitlines()[-1]
        apparmor = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
        if apparmor.exists() and apparmor.read_text().strip() == "1":
            reason += (
                "; kernel.apparmor_restrict_unprivileged_userns is 1, and it is the distribution's"
                " AppArmor profile for bwrap, where it is loaded, that permits it"
            )
        return reason
    return None


def runtime() -> None:
    if shutil.which("bwrap") is None:
        raise SystemExit(
            "bubblewrap is not installed: apt install bubblewrap (or dnf install bubblewrap).\n"
            "Without it and without a container runtime, run this job in the image on a CI\n"
            "runner; a distribution Sage is not this environment."
        )
    reason = user_namespaces()
    if reason:
        raise SystemExit(
            f"unprivileged user namespaces are not permitted here ({reason}).\n"
            "This host is unsupported for the no-runtime path, and this script does not\n"
            "change host policy. Run the job in the image on a CI runner or another host\n"
            "that permits them; do not substitute a distribution Sage."
        )


def command(
    rootfs: Path,
    arguments: list[str],
    binds: list[str],
    environment: list[str],
    directory: str | None,
    image_environment: list[str] = (),
) -> int:
    runtime()
    home = rootfs.parent / "home"
    home.mkdir(exist_ok=True)
    mounts = ["--bind", str(rootfs), "/", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", str(home), "/root"]
    if Path("/sys").is_dir():
        mounts += ["--bind", "/sys", "/sys"]
    # The image's own directories are owned by the account that built it and
    # are not traversable from this one, so a host directory is mounted as a
    # new path rather than over its own: /work for the current directory, and
    # whatever DEST a caller asks for with --bind SRC:DEST.
    mounts += ["--bind", os.path.abspath(os.getcwd()), "/work"]
    workdir = directory or "/work"
    for mount in binds:
        source, _, destination = mount.partition(":")
        source = os.path.abspath(source)
        mounts += ["--bind", source, destination or source]
    variables: dict[str, str] = {}
    for entry in image_environment:
        key, _, value = entry.partition("=")
        variables[key] = value
    variables.setdefault(
        "PATH", "/sage/.venv/bin:/opt/elan/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    variables["HOME"] = "/root"
    variables["TMPDIR"] = "/tmp"
    for entry in environment:
        key, _, value = entry.partition("=")
        variables[key] = value
    # --clearenv: a container runtime gives the process the image's environment,
    # not the caller's. Inheriting the host's PYTHONPATH, LD_LIBRARY_PATH or
    # XDG_* would let it shadow the image's own modules and paths.
    argv = ["bwrap", *mounts, "--clearenv", "--chdir", workdir, "--unshare-pid", "--die-with-parent"]
    for key, value in variables.items():
        argv += ["--setenv", key, value]
    argv += ["--", *arguments]
    # The command's own failure is this tool's exit status, which the caller
    # propagates; raising here would replace it with a traceback.
    return subprocess.run(argv, check=False).returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sage-image.py", description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--reference", default=REFERENCE)
    parser.add_argument("--digest", help="linux/amd64 manifest digest to pin instead of the reference")
    parser.add_argument("--rootfs", type=Path, help="an already unpacked image, instead of the cache")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="fetch and unpack the image")
    commands.add_parser("info", help="print the digests the cache was unpacked from")
    commands.add_parser("check", help="run the image's research environment check")
    run = commands.add_parser("run", help="run a command inside the image")
    run.add_argument("--bind", action="append", default=[], metavar="SRC[:DEST]", help="mount SRC at DEST (default: its own path)")
    run.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    run.add_argument("--chdir", metavar="DIR")
    options, rest = parser.parse_known_args(argv)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if options.command == "run" and not rest:
        parser.error("run needs a command after --")

    record: dict = {}
    if options.rootfs:
        if options.command in ("fetch", "info"):
            parser.error(f"{options.command} maintains the cache; do not combine it with --rootfs")
        rootfs = options.rootfs
    else:
        rootfs = options.cache / "rootfs"
        if options.command == "info":
            record = read_stamp(options.cache) or {}
            if not record:
                raise SystemExit(f"no image unpacked in {options.cache}; run fetch first")
        else:
            if options.command == "fetch" or not stamp_path(options.cache).exists():
                record = unpack(options.cache, options.image, options.reference, options.digest)
            else:
                record = read_stamp(options.cache) or {}
            if options.digest and record.get("manifest") != options.digest:
                raise SystemExit(
                    f"the cache holds {record.get('manifest')}, not the requested {options.digest}; run fetch first"
                )

    if options.command in ("fetch", "info"):
        print(json.dumps(record, indent=2))
        return 0
    if not rootfs.is_dir():
        raise SystemExit(f"{rootfs} is not an unpacked image; run fetch first")
    image_environment = record.get("env", [])
    environment = getattr(options, "env", [])
    if options.command == "check":
        return command(
            rootfs,
            ["/sage/.venv/bin/sage", "docker/research-environment-check.py"],
            [],
            environment,
            "/sage",
            image_environment,
        )
    return command(
        rootfs,
        rest,
        options.bind,
        environment,
        options.chdir,
        image_environment,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
