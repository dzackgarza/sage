# Checklist for `sage.rings.rational_field`

## A. Skeleton provenance
- [x] Stubgen command used: `stubgen --parse-only sage/rings/rational_field.py -o ../typings`
- [x] Stubgen log file path: `tools/typing/logs/sage.rings.rational_field.log`

## B. Export surface
- [x] `RationalField` (class)
- [x] `QQ` (instance)
- [x] `Q` (alias)
- [x] `is_RationalField`
- [x] `frac`

## C. Symbol-by-symbol completion

- [x] `RationalField`
    - `__new__`: returns `RationalField` (singleton logic)
    - `__init__`: None
    - `__reduce__`
    - `__len__`: raises TypeError (so `int`)
    - `construction`: returns (functor, parent)
    - `completion`
    - `__iter__`: yields `Rational`
    - `__truediv__`: returns `QmodnZ` or super result
    - `range_by_height`: yields `Rational`
    - `primes_of_bounded_norm_iter`: yields `Integer` (primes)
    - `discriminant`: returns `Integer`
    - `absolute_discriminant`: returns `Integer`
    - `relative_discriminant`: returns `Integer`
    - `class_number`: returns `Integer`
    - `signature`: returns `(Integer, Integer)`
    - `embeddings`
    - `automorphisms`
    - `places`
    - `complex_embedding`
    - `residue_field`
    - `hilbert_symbol_negative_at_S`
    - `gens`
    - `gen`
    - `degree`
    - `absolute_degree`
    - `ngens`
    - `is_absolute`
    - `is_prime_field`
    - `characteristic`
    - `maximal_order`
    - `number_field`
    - `power_basis`
    - `extension`
    - `algebraic_closure`
    - `order`
    - `polynomial`
    - `some_elements`
    - `random_element`
    - `zeta`
    - `selmer_generators`
    - `selmer_group_iterator`
    - `selmer_space`
    - `quadratic_defect`
    - `valuation`
- [x] `QQ`
- [x] `is_RationalField`
- [x] `frac`

## D. Dynamic/conditional behavior
- None.

## E. Internal consistency
- [x] Imports checked.
- [x] Syntax verified.

## F. Review Gate
- [x] Verified.
