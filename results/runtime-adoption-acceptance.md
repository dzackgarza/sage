# Issue #6 acceptance record

Maps each acceptance clause of
[#6](https://github.com/dzackgarza/sage/issues/6) to the artifact that satisfies it,
and reconciles the issue's literal target with what was actually adopted.

## Target: `b1997dd` (literal) versus `ec386a5b` (adopted)

The issue's table names `b1997dd` as the commit "the published image was built from".
That was true when it was written and is no longer the right target:

* `b1997dd9f1ba` is an **ancestor** of `ec386a5b9b51` (`git merge-base --is-ancestor`
  returns true). Adopting the literal pin today would be a **downgrade** that
  reintroduces two defects already fixed upstream:
  * `a20baff` — `src/sage/libs/meson.build`; without it a reconfigure regenerates
    `config.py` with an empty `MAXIMA_PREFIX` and `sage.symbolic` dies in
    `load(linearalgebra)`.
  * `6dc2659` — the GAP matrix-group packages, which a consumer needed and reported
    absent (`results/gap-capability-absence-chronology.md`).
* The published image has since been built at `6dc2659` (index `sha256:122ccd3a…`,
  config `20fe067d…`), and `develop` past `ec386a5b` is documentation only:
  `git diff --stat ec386a5b9b5..develop -- src/ docker/ build/ justfile pyproject.toml uv.lock`
  reports a single `.md` file.

So "no remaining delta against `b1997dd`" is satisfied in intent and exceeded in
fact: there is no delta against the **current published source**. The literal string
in the issue is stale and wants a one-line edit to `ec386a5b`; that edit is an issue
write, which this session cannot make.

## Clause 1 — `verify` prints no remaining delta

Run after the adoption and again while consumers were active (read-only, no writes):

```
uv.lock                            f070d20194761a12   f070d20194761a12   ok
install-research-repositories.sh   a46fb9a7024d80bc   a46fb9a7024d80bc   ok
research-environment-check.py      57427990eaaf1d10   57427990eaaf1d10   ok
provision-lean-packages.sh         5af7c91b2b9eb994   5af7c91b2b9eb994   ok
julia-launcher.sh                  d1df681a03f2fe84   d1df681a03f2fe84   ok
src/.../meson.build                d8119d97dfa923a7   d8119d97dfa923a7   ok
src/.../libs/meson.build           a25ab4a58e5a788d   a25ab4a58e5a788d   ok

sage HEAD ec386a5b9b51c88c349c0a8c33e74e53f96c7745 (published ec386a5b9b51, pre-adoption b0cd7d86e21e)
sage-indefinite-port: 4f0ee50c3ef4
sage-extensions: 7b222e862145
research: ec1333eeb074
```

`src/.../libs/meson.build` is a check added by this work: the a20baff fix was
previously unpinned, so the file that makes the regeneration correct went unverified.

## Clause 2 — `check` passes

The image's own `docker/research-environment-check.py`, run inside the live rootfs
through the maintained no-runtime path (`job jmw254m3g`, retained log):

```
SageMath version 11.0.beta5, Release Date: 2026-10-28
[peakrss] run: child waited=0 shell_code=0 samples=73
[peakrss] peak tree RSS      : 7862 MiB
[peakrss] low-water MemAvail : 9628 MiB
```

At `ec386a5b` this check also asserts the GAP capability, so it covers the packages
the runtime was missing.

## Clause 3 — runbook status line says executed

`results/runtime-adoption-runbook.md:3` reads
**"Status: executed 2026-11-04 at `ec386a5b`; see `results/runtime-adoption-run-2026-11-04.md`."**

## Clause 4 — the run is recorded under `results/`

Per-step wall clock, from the retained job logs:

| step | command | wall clock | log |
| --- | --- | --- | --- |
| preflight | `runtime-adoption.sh preflight` | <1 s | `jmw25m9g1` |
| source adopt | `git checkout ec386a5b9b51…` in `/sage` | 1.9 s | session |
| sync | `just research-environment-sync` | **5m12.924s** (user 7m56.586s, sys 0m47.354s) | `jmw24x6n0` |
| verify | `runtime-adoption.sh verify` | <0.1 s | this record |
| check | `sage-image.py check` | **2m26s** (73 samples) | `jmw254m3g` |
| check again, bounded | same, `PEAKRSS_LIMIT_MIB=10240` | 42 s (21 samples, warm caches) | `jmw25m9g1` |
| GAP consumer check | `results/consumer-check.py` in the rootfs | 1.6 s | session |

Preflight as recorded in the adoption window:

```
rootfs: /workspace/nucleus/work/home/sage-image/rootfs
no process inside the rootfs
sage HEAD: ec386a5b9b51c88c349c0a8c33e74e53f96c7745
sage diff: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

(`e3b0c442…` is the sha256 of the empty string: a clean working tree.)

## Rollback

* GAP packages and `gac`: `results/gap-capability-installed.txt` lists exactly five
  paths; `MANIFEST=… results/gap-capability-install.sh rollback` removes only those.
* Pre-adoption module, stamps, launcher and distribution list:
  `results/runtime-rollback-snapshot/`.
* The Maxima hand-edit is gone by design and must not be restored; the recipe now
  produces the correct prefix.

## What this record does not claim

That #6 is closed. Issue writes are unavailable to this session (`gh` is
unauthenticated, and the GitHub connector is read-only for issues), so the closure
and the one-line target edit are the reviewing session's to make. The evidence above
is what such a closure should cite.
