# Card 026E: what `primitive_orbit_series` actually returns

Input for lattice-database#16. The card's certification died in the adapter's JSON
emission, `TypeError: Object of type Cardinalities.parent_class is not JSON serializable`,
nested at `primitive_orbits -> O -> constant` (job 128263401273 of run 42326648686). This is
the object it was trying to serialize.

## How it was run

The probe `openmath-026e-cardinality-probe.py`, unmodified, in the pinned image
(`ghcr.io/dzackgarza/sage@sha256:220293469c53…`, unpacked at `~/sage-image/rootfs`), with
the working directory `/repos/lattice-database` so the card it reads is the checkout's:

    docker/sage-image.py --rootfs ~/sage-image/rootfs run \
      --bind <probe>:/probe.py --bind <sage-extensions>:/repos/sage-extensions \
      --env PYTHONPATH=/repos/research/src:/repos/lattice-database/src \
      --chdir /repos/lattice-database -- /sage/.venv/bin/python /probe.py

Three ingredients, and each differs from what is in force today:

| ingredient | revision used | note |
| --- | --- | --- |
| the card | lattice-database `230d41ae` | the image's checkout; the lock pins `d1711db05f` |
| the provider | sage-extensions `3e4812618c` | the lock pin (next image), then `7540ceba` = `main` (what the CI job installs) |
| the image | the pinned develop image | Sage 11.0.beta5, GAP 4.16.1, Julia 1.12.7 |

Same output at both provider revisions, so this is not a stale pin.

## The object

    series groups: ['O', 'O+', 'Otilde', 'Otilde+', 'SO', 'SO+', 'SOtilde', 'SOtilde+']
    groups[O] keys: ['constant', 'w', 'z']
    constant class: Cardinalities.parent_class | module: sage_extensions.categories.sets.cardinals
    constant mro: ['Cardinalities.parent_class', 'Cardinalities.ParentMethods',
                   'Objects.ParentMethods', 'OwnedParent', 'Parent', 'CategoryObject',
                   'SageObject', 'object']
      is_finite: <bound method Cardinalities.ParentMethods.is_finite of 1>
      cardinality: <bound method Cardinalities.ParentMethods.cardinality of 1>
      n: '<absent>'
      value: '<absent>'
      is_integer: '<absent>'
      int(constant) -> 1
      constant.cardinality() -> 1
      constant.is_finite() -> True
    json.dumps(series) raises TypeError: Object of type Cardinalities.parent_class is not JSON serializable
    its repr: {'O': {'constant': 1, 'z': [], 'w': []}, 'SO': ..., ... all eight groups, constant 1}

So `series` is a plain `dict` of eight groups, each a `dict` with `constant`, `z`, `w`. The
`constant` of every group is **a Sage element of the dynamical class
`Cardinalities.parent_class`** — created by `sage_extensions.categories.sets.cardinals`, an
`OwnedParent` under `Parent` — which is a cardinal number with the value 1. It coerces and
prints as `1` (`int()`, `cardinality()`, `is_finite()`, and its own `repr`), but it is not an
`int`, not a Sage `Integer`, and has no JSON hook, so `json.dumps` refuses it. `z` and `w`
are empty lists on this card.

For the adapter, the observable contract is: `constant` is an object that answers
`int(...)`, `...cardinality()` and `....is_finite()` and prints as its value. Whether the
adapter reads it through `int(...)` or the provider returns a plain `Integer` is the owner's
call; nothing here edits the library, the card or the object.

## Two further facts a rerun will run into

1. **The image as it stands today fails earlier.** Its `/repos/sage-extensions` is
   `7b222e86`, and there `primitive_orbit_series` raises

       ValueError: primitive bounded orbit series requires a definite lattice,
                   not Integral lattice of rank 7 and signature (1, 6)

   from `lattice_orbit_invariants.py:136`. That guard is absent at `3e4812618c`, so the
   next published image — the one that carries the lock — reaches the `Cardinalities`
   object and the `TypeError` comes back. A rerun on the current image would report the
   guard, not #16.
2. **The card's revision is older than the lock here.** The probe read the card from the
   image's `lattice-database 230d41ae`; the lock pins `d1711db05f`. The value above is the
   provider's, computed from that card's Gram data, and the card's own content is not
   edited by this run.
