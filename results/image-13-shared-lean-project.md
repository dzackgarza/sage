# image#13: one shared Lean project, always on the latest Mathlib

> **Superseded in two points** by the owner's decision of 2026-11-10, implemented in
> `results/image-13-head-per-build.md`: every build now resolves the Mathlib head
> (incremental builds included, rebuilding the closure only when it moved), and the
> image's check validates the image's own project only, with
> `--allow-lagging-lean-checkouts` deleted. The sections below that describe an
> incremental build keeping its project, and the flag, are history.

Owner's decision (issue body, 2026-11-10): the image carries exactly one Lean
project, `mathlib4` at the head of `leanprover-community/mathlib4` master, on the
toolchain that revision pins, with its whole dependency closure built inside it and
Mathlib's oleans from the official cache. Every Lean checkout under `/repos` resolves
Mathlib and its dependencies from it. No fixed release, no per-revision checkout, no
views, no second toolchain.

## What the change does

`docker/provision-lean-packages.sh` is rewritten around that one project.

* **A build with no project resolves the head.** `git ls-remote … refs/heads/master`
  for one revision, a `--depth 1` checkout of exactly that revision into
  `/opt/mathlib`, `elan toolchain install` + `elan default` of the toolchain
  `lean-toolchain` in that revision names, `lake exe cache get` (official cache),
  `lake build Mathlib` (the closure, once). No tag and no revision is written in the
  script: the head is whatever master is at build time.
* **The record.** `/opt/lean-image.json` states `project`, `repository`, `revision`,
  `master_head_at_resolution`, `toolchain`, `cache` and `resolved` (UTC). This is
  what a consumer reads for provenance, and what the environment check asserts
  against.
* **Every checkout, bound to it.** For each Lean checkout under `/repos`, one link
  per package its own `lake-manifest.json` pins, in the packages directory *its*
  lakefile declares: `mathlib` → the project, Mathlib's closure →
  `/opt/mathlib/.lake/packages/<name>`, a research package (e.g. `lean_categories`)
  → `/repos/<name>`, and a package nothing in the image carries (e.g. `BrauerGroup`,
  `checkdecls`) → `/opt/lake-packages/<name>@<rev>`, cloned once per revision and
  never built. A link is only made when the target's `HEAD` is exactly the pinned
  revision; a link an earlier run left at another revision is removed.
* **A disagreement is named, not papered over.** A pin the image does not carry
  prints
  `error: <checkout> pins <package> at <revision> and the image carries <revision>:
  the checkout does not follow the image`, and the same for a second toolchain.
  Nothing in a checkout is rewritten: its manifest stays what its repository
  published, and `/repos` heads are untouched.
* **Deleted, as the issue requires:** `/opt/lake-packages/mathlib@<revision>`,
  `/opt/lake-views` and its `index.json`, the per-checkout overrides, and the
  launcher's `--lean-view` (with `lean_view_mounts`, `resolve_in` and `git_head`,
  which existed only for it). `/opt/lake-packages` survives only as the store for a
  package neither Mathlib's closure nor a checkout provides — it holds no Mathlib and
  no view.

`docker/research-environment-check.py` then asserts, in the image: the recorded
revision is the one checked out; `master_head_at_resolution == revision`; the
recorded toolchain is the one `lean-toolchain` pins and elan's default; Mathlib's
olean and every package the project's own manifest pins are present at exactly those
revisions with a build directory; `lake env lean --version` reports the pinned
toolchain; `lake build Mathlib` exits 0; and, per checkout, an `import Mathlib` plus
`lake env lean --version` on the image's Mathlib — or a loud, named disagreement.

The disagreement fails the check. The build passes `--allow-lagging-lean-checkouts`
so an image can be published while the Lean repositories catch up; a consumer running
the check without the flag gets the failure. The pin moves are lean-categories#118
and lean-cas-dsl#90 and are not this repository's work.

## Consequence to expect on the next image run: `no-runtime` in
`research-environment-image.yml` runs `docker/sage-image.py check`, which runs the
check without the flag, so that job fails while any Lean checkout lags — with the
named lines. That is the issue's loud failure reaching a consumer, and it is why the
flag is only on the build's own invocation. If the owner would rather the image's
own run stays green and only a hand-run check fails, the one-line change is passing
`--allow-lagging-lean-checkouts` in that job's `check` call — a workflow change, so
a patch.

## The one reading worth arguing about

The issue says *each image build* resolves the head. As built, a **full** build
resolves the head and an **incremental** build (`FROM` the published image) inherits
the project its base carries and keeps it. The reason is image#9: resolving the head
on an increment means rebuilding Mathlib's closure on every source push, which is
the 10.7 GiB layer, and that would undo the only part of the pull cost that is under
this repository's control. So the image moves to a new Mathlib head when it is built
in full (a Dockerfile change, a deletion, or a dispatch), and `/opt/lean-image.json`
is what says which head it is on. If the owner wants a Mathlib move on demand without
a Dockerfile edit, the mechanism to add is a `full_rebuild` dispatch input on the
workflow — which is a workflow change and so a patch, not part of this push.

## Verified here, and not

`python3 -m pytest -o addopts= docker/tests/test_lean_shared_project.py` → **13
passed**. The tests run the real script and the check's real Lean block (extracted
from `research-environment-check.py`, with only the five absolute paths pointed at a
fixture) against fixture repositories:

| test | what it pins |
| --- | --- |
| the project is linked in the declared directory | the link, and that the manifest is not edited |
| Mathlib's closure is the project's | `batteries` links into `/opt/mathlib/.lake/packages` |
| a package no one carries is fetched once | a real clone into `<name>@<revision>`, linked, and reused on a second run |
| a pin the image does not carry | the exact loud sentence, both revisions, and that nothing is linked |
| no second toolchain | the toolchain sentence |
| a stale link is removed | a link at another revision does not survive |
| the project at another revision / without its olean | a failed image, not a warning |
| a build with no project | resolve, checkout, record, link — with `elan`/`lake` stand-ins, so this asserts the sequencing and the record, not Lean |
| the check's Lean block, three ways | follows → exit 0 with the report; lags → exit 1 naming both revisions; with `--allow-lagging-lean-checkouts` → exit 0 with the warning |

**Not verified here**, and this is what the acceptance run has to settle: no image
has been built with this change, so `lake exe cache get`, `lake build Mathlib`, the
closure's build time, the new layer's size, and whether the check's `lake env` calls
return under the runner's own container are unmeasured. `lake env` famously does not
return under PRoot (see `docker/SAGE-ENVIRONMENT.md`), so the check's Lean part was
never executed outside a container in this work either.

## Acceptance, to paste from inside the built image

```sh
cat /opt/lean-image.json
git -C /opt/mathlib rev-parse HEAD
cat /opt/mathlib/lean-toolchain
cd /opt/mathlib && lake env lean --version

# every Lean checkout that follows the image
for d in /repos/*/; do
  [ -f "$d/lean-toolchain" ] || continue
  printf 'import Mathlib\n#check (Nat.add_comm : ∀ a b : Nat, a + b = b + a)\n' > /tmp/m.lean
  ( cd "$d" && lake env lean /tmp/m.lean ) && echo "OK $d"
done

# the check itself: the disagreement is loud, and the build's flag is the opt-out
sage docker/research-environment-check.py            # exit 1 while a checkout lags
sage docker/research-environment-check.py --allow-lagging-lean-checkouts
```

The first line of the check's Lean section prints
`the shared Lean project: mathlib <revision> on <toolchain> (master head resolved at
<UTC>), closure built in /opt/mathlib: <closure>`, and the revision it names is what
`git ls-remote https://github.com/leanprover-community/mathlib4 refs/heads/master`
said at the build's start.

No workflow file changes for this issue, so there is no patch to land: the
Dockerfile change puts `docker/research-environment.Dockerfile` in the run's diff,
which is what makes the selector build in full — and a full build is what resolves a
fresh Mathlib head.
