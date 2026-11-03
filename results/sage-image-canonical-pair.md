# The canonical pair in the research lock

## What changed

| Lock entry | Before | After |
| --- | --- | --- |
| `sage-indefinite-port` | `86d860a428c2…` (reads the predecessor research library) | `4f0ee50c3ef432681ecdbbd7a5a7f5adb244d83b` |
| its dependencies | `dzack-research` | `pynormaliz`, `sage-extensions` |
| `sage-extensions` | `441519c574ce…` | `7b222e86214524a53802350f3cfda9c513707600` (requirements unchanged) |

The port at `4f0ee50c` declares `sage-extensions @ git+…@7b222e86214524a53802350f3cfda9c513707600`
and `PyNormaliz`, and no predecessor research library; its own record names the
verified pair as port main plus that sage-extensions revision. Every other git
source keeps its revision, and `dzack-research` stays at `ec1333e` as content for
the consumers that still import it — the port no longer reads it, so the stale
port/post-move research mismatch is gone rather than reverted.

## Checks added to the image

`docker/research-environment-check.py`, beside the existing bliss and Julia
checks:

* the installed requirement of `sage-indefinite-port` names `sage-extensions`
  and names no research library;
* `Lattices.__module__` is `sage_extensions.categories.lattices`;
* an isometry exists between a lattice and the same lattice in another basis,
  and none exists between lattices of different determinant;
* the hyperbolic plane's `O`, `Aut` and stable orthogonal group have their
  recorded orders (4, 4, 4).

## Evidence

* `uv sync --locked --dry-run` against the edited lock, inside the image:
  accepted, and reports `sage-extensions @ …@7b222e86…` and
  `sage-indefinite-port @ …@4f0ee50c…`.
* The smoke block run in the image (Sage 11.0.beta5, CPython 3.14.10) with the
  two checkouts at the pinned revisions and the port installed from its own
  pyproject: passes, `requires: ['sage-extensions @ …@7b222e86…', 'PyNormaliz']`.
* The same block against the image as published: fails at the requirement
  assertion with `['dzack-research @ git+https://github.com/dzackgarza/research']`,
  which is the stale pair this commit removes.
* Full check, in one run inside the image with the modified script bound in, the
  two checkouts at the pinned revisions, the local bliss repair, the julia
  launcher and the port's new metadata: passes, ending at
  `SageMath version 11.0.beta5, Release Date: 2026-10-28` (exit 0).
* Without the port's new metadata the same run stops at the requirement
  assertion instead, so the check separates the two states.

Publication remains held; nothing is pushed and no other repository moved.
Commits: `6614e1f` on `develop` (this change), on top of `938d473` and the
earlier environment work.
