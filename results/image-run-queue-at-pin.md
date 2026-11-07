# Image publication state at the provider pin

Checked against GitHub's own records (workflow `research-environment-image.yml`), not inferred:

| run | revision | state | what it would carry |
| --- | --- | --- | --- |
| 42379122786 | `552169cece` — the pin commit | **queued / pending** | the chamber step and its failure propagation (from `f62e005ec8`), and the provider pinned at `240cd3f8` with the matching metadata and lock |
| 42366092165 | `c5e1ae6e09` | in progress | the comparator fix, **not** the provider pin |
| 42362483952 | `b6b4590f7e` | completed, failure | the run whose eight-vertex simplex and `families.yaml` failure started these units |

**Nothing is running at `01585742386`.** There is no image run at that revision and there will not
be one from a push: that commit changes only `results/`, and the workflow's `push` trigger filters
on `pyproject.toml`, `uv.lock`, `justfile`, `meson.build`, `src/**`, `build/pkgs/**`, `docker/*`
and the workflow file itself. The run at `552169cece` — its immediate parent in content terms —
is the one to watch, and it is queued.

One hazard worth naming: the image workflow's runs cancel in favour of a newer push on the same
path filter. A further commit touching any of those paths would cancel `42379122786`. Commits that
touch only `results/` do not trigger it and do not cancel it.

## What that run is expected to answer

The consumer-acceptance job of that run performs both calls, on the image it publishes:

- **the owner contracts** — `tests/lattices/test_lattice_database_owner_contracts.sage`, whose
  twelve tests include `test_positive_a2_genus_and_orthogonal_group_are_owned_by_the_lattice`. The
  deciding line is `12 passed`, or the failing assertion's message; the same call at the same
  provider passed locally in 264.00 s (results/owner-contracts-240cd3f8.log).
- **the chamber input path** — the `Read the I_{1,8} chamber with CoxIter` step. The deciding lines
  are the graph it hands over (nine vertices, eight edges), `Number of vertices: 9`,
  `Q[sqrt(2)]`, the Coxeter matrix, and `labelled adjacencies equal to its edge list`. A step that
  swallowed its own assertion would now fail instead: the step is `set -euo pipefail`.

#15 and #18 stay open until those two results come back from a published image. The queued run is
also the first image to carry the provider pin, so its `certify` step and its lock are the pin's
real test.
