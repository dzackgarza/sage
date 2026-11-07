# lattice-database 9fa82dcb: storage tests and the real recovery regression

Execution record for lattice-database#17 at `9fa82dcb80f273d47184ca56671edb85b1fc4b21`
(GitHub-verified), in the supported published image
(`ghcr.io/dzackgarza/sage@sha256:220293469c53…`, unpacked at `~/sage-image/rootfs`), on a
real checkout with its owned imports and the retained artifacts bound into the path the
owner's scripts expect.

    lattice-database  9fa82dcb80f273d47184ca56671edb85b1fc4b21
    sage-extensions   3e4812618ce0d5f67dc88959a161ac6ebeb75da2   (provider, lock pin)
    sage-indefinite-port 991b88b095a42a1e3679569ea42328c900c120f6 (held)
    research          dbf178cf30c1d26e5f98753c1d9cdbcc16ee3d25   (lock pin)

The artifacts are the retained originals of run 42326648686: 60 per-tag directories,
4.0 MB, copied unmodified into `<checkout>/attachments/you-work-the-github-s6pa/extracted/`.
Their SHA256 for `verify-recovered-old.py` matches the file in the lattice-database project's
attachments (`8682db92bec44792…`); nothing in that project was written.

## The three storage/persistence modules — all green

    pytest -q tests/test_failures.py tests/test_merge.py tests/test_persist.py
    13 passed in 31.08s

Both fixtures that failed at `33534455` and again at `ca17c53e` now pass: the ledger test keeps
`0012`'s two computations in shard `2f` and still rejects a misplaced duplicate, and
`failure_attempt()` supplies a real `datetime`. Log: results/latticedb-9fa-storage-tests.log.

## The recovery regression on the retained artifacts

**1. Recover every artifact — passed, 60 tags, no conflicts.**

    results/recover-42326648686.py attachments/…/openmath-certify-42326648686
    … 6JRU: card reconciled with 0 conflict(s) … 6JRW: …
    no conflict: every field the artifacts carry is on the cards, in the shards and in the ledger
    exit 0

**2. Verify recovered values and recompute certificates — not completed (harness bound).**
The run was bounded at 1800 s and reached that bound (`exit 124` at 30:01, 17:25 CPU, one
thread, RSS 1.35 GB); the verifier prints only at the end, so no partial finding exists.
Recomputing every certificate of 60 cards through `genus.certified_value` needs a longer
bounded window than this pass allowed. This is a limit of my invocation, not a result about
the verifier: nothing here says the values disagree.

**3. The revision's own verifier against the defect cases — PASS.**

    results/regression-recovery-defects.py            → exit 0
    preserved original attempt hashes: ['d75a9ad628461d9f….', 'aaaa….']
    # removing the original attempt from a copy only:
    1 recovered artifacts verified against their own patches
    1 problems found
       0066 integral.primitive_orbits: original failure attempt d75a9ad628461d9f is missing
    # deleting the on-card derive in a second copy:
    2 problems found
       0066: certifications.derive missing
       0066 derive: on-card certification is missing although the artifact supplies the corresponding certificate
    PASS: every exercised owner projection and failure-history obligation was met

Both rejections are intended, each names the field or the attempt, and the preserved-later
attempt survives the first mutation.

**4. The old verifier, as the red side — it rejects valid recovered data.**

First attempt passed `attachments/regression-old-verify/verify-recovered-old.py` as a
*relative* path, and the runner resolves the verifier from the temporary copy it makes under
`attachments/`, so it died with

    can't open file '…/attachments/recovery-check-j0ae42a1/attachments/regression-old-verify/verify-recovered-old.py'

— a fixture-path error on my part, and not evidence about any verifier. With the absolute path
the old verifier runs and imports normally, and fails at the **first** stage, the unmodified
recovered data:

    results/regression-recovery-defects.py /repos/lattice-database/attachments/regression-old-verify/verify-recovered-old.py
    $ … verify-recovered-old.py artifacts
    1 recovered artifacts verified against their own patches
    1 problems found
       0066 integral.primitive_orbits: original failure attempt d75a9ad628461d9f is missing
    the actual recovered data should verify; exit 1

So the old verifier reports the attempt missing on data where it is present, which is exactly
the defect the 9fa verifier corrects: the same input that stage 3 rejects **after** removal is
rejected by the old verifier **before** it. The runner stops at that point, so the mutation
stages are not reached with the old verifier — the red side is the false rejection, not a
stricter one.

**5. The revision's own verifier test — passed.**

    pytest -q tests/test_verify_recovery.py → 1 passed in 110.02s

## What this leaves open

- **The full 60-tag verification is unrun**: step 2 above, needing a window longer than 30
  minutes. #17 stays open until it completes against the artifacts.
- **The certify path** is the orchestrator's single queued GitHub run on `main`; no local
  attempt was repeated here.
- **#15** stays blocked by sage-extensions#291, untouched.
