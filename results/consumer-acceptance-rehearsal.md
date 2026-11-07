# The consumer-acceptance steps, rehearsed at the pinned pairing

Everything below was run inside the unpacked pinned image
(`ghcr.io/dzackgarza/sage@sha256:220293469c53…`, `~/sage-image/rootfs`) through
`docker/sage-image.py --rootfs … run`, with the checkouts bound at the revisions
`uv.lock` holds so that the pairing is the one the next image carries rather than the one
this rootfs was built with:

    --bind .scratch/wt-se:/repos/sage-extensions                 # 3e4812618ce0d5f67dc88959a161ac6ebeb75da2
    --bind .scratch/wt-port:/repos/sage-indefinite-port          # 991b88b095a42a1e3679569ea42328c900c120f6
    --bind .scratch/research-pin:/repos/research                 # dbf178cf30c1d26e5f98753c1d9cdbcc16ee3d25
    --bind .scratch/qc-infra:/qc-infra                           # ai-review-ci main 14816b70
    --env PYTHONPATH=/qc-infra/tool-artifacts/pytest_plugins
    --chdir /repos/sage-extensions

The image's own `/repos` is older than the lock (sage-extensions `7b222e86`,
sage-indefinite-port `4f0ee50c`), so a run that binds only some of the checkouts measures a
pairing that exists nowhere. That mistake was made first and is recorded at the end
because it is what the pin assertion in `results/tco-provenance-consumer-workflow.patch`
now catches.

## sage-extensions' isotropic-line-orbit suite — passes

    /sage/.venv/bin/python -m pytest -o addopts= --durations=0 -q -p qc_sage_session \
      /repos/sage-extensions/tests/lattices/test_isotropic_line_orbits_of_small_indefinite_lattices.sage

    3 passed in 492.59s (0:08:12)

    485.09s  test_the_line_counts_of_the_three_groups_are_the_derived_ones
      6.55s  test_the_rank_five_shadow_has_one_primitive_isotropic_plane_orbit
      0.04s  test_the_two_witness_vectors_of_l_9_are_primitive_isotropic_of_divisibility_three

The line-count test dominates because on `991b88b0` the port enumerates through the Hecke
engine (repeat Julia workers) where `4f0ee50c` did not; the same three tests took 88 s
there. 8 minutes is the number the job's 60-minute budget has to hold, not 88 s.

## lattice-database's owner contracts — one failure, an owner defect

    /sage/.venv/bin/python -m pytest -o addopts= --durations=0 -q -p qc_sage_session \
      /repos/sage-extensions/tests/lattices/test_lattice_database_owner_contracts.sage

    1 failed, 11 passed in 256.62s (0:04:16)

    59.58s  test_positive_a2_genus_and_orthogonal_group_are_owned_by_the_lattice
    20.82s  test_primitive_orbit_series_counts_primitive_isotropic_lines

The failure is `test_root_and_theta_catalogue_invariants_are_owned_by_the_lattice`, and it
is sage-extensions' own code, at the pin:

    lattice.reflective_root_system_components()
      lattices.py:7149        -> _reflective_root_system_components(self)
      definite_lattices.py:497 -> DefiniteLattices(...).reflective_roots()
      lattices.py:9122        -> self.roots_of_square(sign * length)
      lattices.py:7095        -> _roots_of_square(self, square)
      definite_lattices.py:370 -> _shell(lattice, square, _square_shell(positive_gram, target, True))

    AttributeError: 'int' object has no attribute 'parent'

`_roots_of_square` (definite_lattices.py:368) computes `target = int(sign * square)` and
`_square_shell` (line 294) calls `target.parent()`. The sibling `_vectors_of_square`
(line 345) keeps the ring element and does not hit this. This is existing
sage-extensions#291, confirmed in its own tracker with this run; **it is not repaired from
this repository**, and sage#15's owner-contracts step stays red until sage-extensions
fixes it. The step's own defect — it read that module out of `/repos/lattice-database`,
which has no `tests/lattices` — is `results/owner-contracts-checkout-workflow.patch`.

### The failure the stale rootfs manufactures

Bound as sage-extensions `3e4812618c` + the image's own port `4f0ee50c` (a pairing no
image has), two isotropic tests fail in the port at
`isotropic_induction.py:151`, `int(moved(label))` on an `OwnedJoinCategory.element_class`,
and one owner contract fails in the same way at `recursive.py:154`. `991b88b0` replaces
that call with `_integer(moved(label))` and its own comment names the `TypeError`; both
suites pass as above once the port is the pin. A failure at the seam between two
checkouts says which pairing it ran in before it says anything about either repository.

## The T_Co step's provenance, and why `direct_url.json` is not it

`distribution(name).read_text("direct_url.json")` for both packages:

    {"url": "file:///repos/sage-indefinite-port", "dir_info": {"editable": true}}

No `vcs_info`, so `commit_id` reads `None` — for the port *and* for the provider it
declares in `pyproject.toml`'s `[tool.uv.dependency-metadata]`, sage-extensions. The
revision that ran is the checkout the imported module lives in, held against the image's
own `/sage/uv.lock`:

    sage-indefinite-port: direct_url.json commit_id None
    sage-indefinite-port: imported from /repos/sage-indefinite-port/src/sage_indefinite_port/__init__.py
    sage-indefinite-port: checkout /repos/sage-indefinite-port at 991b88b095a42a1e3679569ea42328c900c120f6, held 991b88b095a42a1e3679569ea42328c900c120f6
    sage-extensions: direct_url.json commit_id None
    sage-extensions: imported from /repos/sage-extensions/src/sage_extensions/__init__.py
    sage-extensions: checkout /repos/sage-extensions at 3e4812618ce0d5f67dc88959a161ac6ebeb75da2, held 3e4812618ce0d5f67dc88959a161ac6ebeb75da2

Held against a lock that disagrees, the same code stops the step with the pair it found:

    AssertionError: sage-indefinite-port: the checkout is 991b88b095a42a1e3679569ea42328c900c120f6,
                    the lock holds 4f0ee50c3ef432681ecdbbd7a5a7f5adb244d83b

## The collector's path

The job's `-p qc_sage_session` needs the plugin directory on `PYTHONPATH`. The image
installs no `qc_` distribution, and `ai-review-ci` keeps the four of them at
`tool-artifacts/pytest_plugins` — there is no `scripts/pytest_plugins`. Both values, in the
image, with the plugin directory laid out as the checkout leaves it:

    PYTHONPATH=…/.qc-infra/scripts/pytest_plugins
      ImportError: Error importing plugin "qc_sage_session": No module named 'qc_sage_session'
    PYTHONPATH=…/.qc-infra/tool-artifacts/pytest_plugins
      3 tests collected in 1.77s

That is landed (b6b4590f); the four-spinor step, gated behind `inputs.sage_source_sha`,
had carried the wrong value since it was written.

## Not covered here

The 6JRR certification, the research record reproductions and the CoxIter reading are
separate runs; this file says nothing about them. The record steps' cost is not in the
table above, so the job's 60-minute budget against 8:12 + 4:16 + ~11 min for T_Co plus a
certify bounded at 20 minutes has not been added up with them in it.
