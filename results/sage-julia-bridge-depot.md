# `sage_julia_bridge` and the missing JSON

Reported symptom: `label.even_overlattice_inclusions()` aborts the bridge at
`/repos/sage-julia-bridge/src/sage_julia_bridge/julia_bridge.jl:2` with
`ArgumentError: Package JSON [682c06a0-de6a-54ab-a142-c8b1cf79cde6] is required
but does not seem installed`.

## The three pieces

| Piece | Where | Content |
| --- | --- | --- |
| Bridge project | `/repos/sage-julia-bridge/src/sage_julia_bridge/julia_env/Project.toml` | `JSON`, `Oscar = 1.7.1` |
| Bridge manifest | same directory, `Manifest.toml` | pins JSON 1.13.4, `git-tree-sha1 = 06d90f69…` |
| Installed depot | `/opt/julia-depot` (image layer) | JSON, Oscar and the rest, instantiated at build time by the bridge's own `just julia-deps` (`Pkg.instantiate()` + `Pkg.precompile()`) |

The bridge starts Julia as
`julia --project=<that julia_env> --startup-file=no --history-file=no
--color=no julia_bridge.jl` (`interface.py`, `_ensure_process`), with whatever
environment it inherits, and `julia_bridge.jl:2` is `import JSON`.
`--startup-file=no` means nothing in a startup file can repair the depot path.

## Reproduction in the shared image

The image declares `JULIA_DEPOT_PATH=/opt/julia-depot:` in its OCI config. A
container runtime applies that to every process; a runner that starts a process
in the unpacked filesystem does not — raw PRoot over the same rootfs has no
`JULIA_DEPOT_PATH` at all. Removing the variable reproduces the reported
failure exactly:

```sh
docker/sage-image.py run -- /bin/sh -c \
  "env -u JULIA_DEPOT_PATH /sage/.venv/bin/python -c \
   'from sage_julia_bridge import Julia; j=Julia(); print(j.eval(\"1+1\"))'"
# ERROR: ArgumentError: Package JSON [682c06a0-de6a-54ab-a142-c8b1cf79cde6] is
# required but does not seem installed: - Run `Pkg.instantiate()` ...
# in expression starting at /repos/sage-julia-bridge/src/sage_julia_bridge/julia_bridge.jl:2
```

With the variable present (the image's own value, or the host launcher's
`/root/.julia:/opt/julia-depot:`) the same call returns `2`. So the provisioning
gap is not a missing package in the image: it is that resolution depended on
the caller carrying the image's environment.

## Fix (image owner)

`docker/julia-launcher.sh` is installed as `/usr/local/bin/julia` by
`docker/research-environment.Dockerfile` instead of a symlink to
`/opt/julia/bin/julia`. It adds `/opt/julia-depot` to whatever
`JULIA_DEPOT_PATH` the caller has, once, and execs the real binary:

| caller's value | launcher presents |
| --- | --- |
| unset | `/opt/julia-depot:` |
| `/tmp/other` | `/tmp/other:/opt/julia-depot:` |
| `/root/.julia:` | `/root/.julia:/opt/julia-depot:` |
| `/root/.julia:/opt/julia-depot:` | unchanged |

No consumer installs JSON, Oscar or anything else: every one of them reaches
Julia through `PATH`.

## Smoke check

`docker/research-environment-check.py` now also runs, with `JULIA_DEPOT_PATH`
removed from the environment, a bridge session that asserts
`JSON.json((a=1,))` through it, and asserts the same call on the session it
already holds. Verified against the published image: with the launcher the
check passes, without it the bridge raises the same `ArgumentError`, so the
image build fails on the published configuration and passes on the fixed one.

## Untouched

`docker/research-repositories.txt` pins the research checkouts, including
`sage-julia-bridge`; none of them changed. A bridge checkout edited inside the
persistent `/repos` volume brings its own `Project.toml`/`Manifest.toml`, and
its `just julia-deps` is the sanctioned way to instantiate that revision into
the writable depot — not an ad-hoc `Pkg.add` in a consumer.

Publication is held with the rest of the `develop` work: locally `938d473`,
nothing pushed, exports in `patches/0001…0006` and `patches/sage-bliss-fix.bundle`.
