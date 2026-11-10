# image#13, second batch: every build resolves the Mathlib head; the check is the image's own

The owner's decision of 2026-11-10 settled the two points the first batch left open.
Both are implemented here; the workflow change they need is
`results/mathlib-head-workflow.patch` (workflow files are landed by the orchestrator,
not pushed from here).

## 1. Every build resolves the head, incremental builds included

`docker/provision-lean-packages.sh` no longer keeps an inherited project: it takes
the head of `leanprover-community/mathlib4` master for the build it is part of, and

* when the record in the image names that same revision, **nothing is written** — no
  clone, no `cache get`, no build, no record rewrite — so the files keep their
  content and the layer that holds them is reused;
* when the head has moved (or there is no project), it checks out the new revision,
  removes the whole of the old `.lake` — a Lean release refuses another release's
  oleans, packages included — installs the toolchain that revision pins as elan's
  default, takes Mathlib's oleans from the official cache, builds the closure once,
  and rewrites the record.

The head is a **build input**, which is what makes the first case a cache hit rather
than a rebuild: the workflow reads it when the build starts and passes it as
`MATHLIB_REVISION`, and both Dockerfiles declare that `ARG` immediately before the
sync step, so an unchanged head leaves that step's cache key unchanged and a moved
head does not. Without the value — a local run, an unpacked image — the script reads
the head itself.

The workflow patch does three things: a step that resolves the head and prints it
(`this build carries mathlib4 master at <rev>`, and fails if git reports anything
that is not a 40-character revision); `MATHLIB_REVISION` in both builds' `build-args`
(the image build and the lock export, so they share one head); and the label
`dev.dzackgarza.mathlib.revision=<rev>` beside `org.opencontainers.image.revision`,
so the image says which Mathlib it carries without anyone pulling it.

Verified locally: the patch applies cleanly to the committed workflow
(`git apply --check`), the result parses as YAML, the step's script was run against
the live registry (`this build carries mathlib4 master at 68dd2955f557…`) and its
guard rejects both `not-a-sha` and an empty value.

## 2. The image's check is about the image's own project

`docker/research-environment-check.py` now asserts only what the image carries:

* the record names one revision, and it is the tree's `HEAD` and the head the build
  resolved;
* that revision's toolchain is what `lean-toolchain` pins and elan's default;
* Mathlib's olean is there, and every package the project's own manifest pins is a
  checkout at exactly that revision with a build directory;
* `lake env lean --version` reports the pinned toolchain;
* `lake build Mathlib` exits 0, and `import Mathlib` elaborates through the project's
  own Lake environment.

It reads nothing under `/repos`. `--allow-lagging-lean-checkouts` is gone, and an
unknown argument is a failure (`unknown argument(s): …`). A lagging repository now
fails in its own CI, which is lean-categories#118 and lean-cas-dsl#90; the image's
run reports the disagreement in provisioning's log as a `note:` with both revisions
and carries on, exit status untouched.

`docker/research-environment.Dockerfile` drops the flag from the check's `RUN`.

## Tests

`python3 -m pytest -o addopts= docker/tests/test_lean_shared_project.py` → **14
passed**, through the real scripts:

| test | what it pins |
| --- | --- |
| an unchanged head reuses the project and touches nothing | record bytes and mtime unchanged, and a `lake`/`elan` that fail if ever called is never called; both checkouts still served from the project |
| a moved head rebuilds the closure and records the new revision | the old `.lake` is gone (a marker file planted in a dep's build tree does not survive), `elan toolchain install`/`default` name the new revision's toolchain, `lake exe cache get` and `lake build Mathlib` ran, the record names the new revision and toolchain |
| the dry run of a moved head | prints the move, writes nothing, checks nothing out |
| a build with no project | resolves the head, checks out, records, links — with `elan`/`lake` stand-ins, so this asserts the sequencing and the record |
| a pin the image does not carry | a `note:` naming the checkout and both revisions, exit 0, nothing linked, nothing on stderr |
| no second toolchain | the same, for the toolchain |
| a stale link is removed | a link at another revision does not survive |
| the check's own Lean block, extracted from the file | validates the project, prints its four lines, mentions no checkout, passes with a lagging checkout present, rejects the removed flag, and fails when the record disagrees with the tree |
| a record that claims a build the tree does not hold | a failed image, naming the remedy |

`bash -n`, `py_compile` and ruff are clean on the touched files; the other
`docker/tests` suites are unaffected.

## Not verified here

No image has been built with either batch. `lake exe cache get`, the closure build,
the `.lake` removal's effect on the new layer's size, and the check's `lake env`
calls inside a container are unmeasured — the check's Lean part has never run
outside a container in this work, and `lake env` does not return under PRoot. The
acceptance output is the image run's check lines, which the orchestrator reads.

## Consequence worth stating once

When the head moves, an incremental build appends a fresh closure layer on top of
the base's — OCI layers only add — so that image carries the old ~10.7 GiB closure
underneath the new one until a full build replaces it. That follows from item 1 as
written (increments rebuild the closure rather than refusing to run); if the extra
weight is unwanted, the workaround is to force a full build whenever the label
`dev.dzackgarza.mathlib.revision` of the base differs from the head just resolved —
one condition in the selector step, and now possible to write because the label
exists. It is not in the patch, because it would override the decision as stated.
