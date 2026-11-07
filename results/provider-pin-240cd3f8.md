# The provider pin: sage-extensions at `240cd3f8`

The image's provider is pinned to the reviewed repair of sage-extensions#291:
`240cd3f845fe2b2d5a46501ae628ccbbb9708c2a`.

## What had to change, and why three edits are one change

`uv lock --upgrade-package sage-extensions` resolves the branch tip, and the tip has moved past the
reviewed commit — it took `0eba9f9c` and would have shipped #296's work unreviewed. A requirement
naming the revision was refused instead:

    Requirements contain conflicting URLs for package `sage-extensions` in split ... :
      - git+https://github.com/dzackgarza/sage-extensions@240cd3f8…
      - git+https://github.com/dzackgarza/sage-extensions

A bare URL and a revision-pinned URL are different requirements to uv, and two other packages
declare the bare one: `sage-indefinite-port` (through its existing
`[[tool.uv.dependency-metadata]]` entry) and `dzack-research` (through its own pyproject, read as
real metadata). So the pin is one change in three parts, all in the repository's existing
mechanism:

1. `[tool.uv.sources] sage-extensions` gains `rev = "240cd3f8…"` — the pin itself;
2. the `sage-indefinite-port` metadata entry states the same revision, as its comment requires;
3. a `dzack-research` metadata entry, restated from research's pyproject at `dbf178cf30` with the
   revision substituted, so that its requirement is the same requirement.

Part 3 is a copy of another repository's dependency list and will go stale silently if research's
dependencies change; its comment says so. That cost was accepted because `[tool.uv]
override-dependencies` is the alternative, and it previously replaced every editable checkout with
a git URL (the editable-install defect this project already paid for once).

## The lock, and the checks

    uv lock --upgrade-package sage-extensions
      Resolved 317 packages in 4.68s
      Updated sage-extensions v0.1.0 (3e481261) -> v0.1.0 (240cd3f8)          exit 0
    uv lock --check                                                          exit 0
    uv lock --upgrade-package sage-extensions   (again, idempotent)          exit 0
    uv sync --dry-run                                                        exit 0
    taplo format --check pyproject.toml                                      exit 0

`uv lock --check` passing is itself new information: it failed for months on the sibling URL
conflict, and now resolves 317 packages and agrees with the lock.

The lock records the pin as
`source = { git = "https://github.com/dzackgarza/sage-extensions?rev=240cd3f8…#240cd3f8…" }`.
Everything else is held: `sage-indefinite-port 991b88b0` (paused, unchanged),
`dzack-research dbf178cf30`, `latticedb d1711db05f`, and every image component untouched.

## The evidence this pin rests on

The owner-contract call at exactly this provider — `12 passed in 264.00 s`, including
`test_positive_a2_genus_and_orthogonal_group_are_owned_by_the_lattice`, which failed at
`definite_lattices.py:294` before the repair. Log: results/owner-contracts-240cd3f8.log.

What is **not** part of this: the 6JRR certificate. A certification run is in flight at
`--workers 1`; whatever it does, it is a separate consumer result and not a precondition for
fixing a proven owner-contract dependency. Publication still needs the actual workflow run at this
pin, in an image built from it — nothing here is that run.
