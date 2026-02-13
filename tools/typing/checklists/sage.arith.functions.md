# Checklist for `sage.arith.functions`

## A. Skeleton provenance
- [x] Stubgen command used: `stubgen-pyx src/sage --file arith/functions.pyx --output-dir typings/sage/arith`
- [x] Stubgen log file path: `tools/typing/logs/sage.arith.functions.log`

## B. Export surface
- [x] `LCM_list`
- [x] `lcm`
- [x] `LCM` is NOT exported by this module (it is an alias in `sage.arith.all`).

## C. Symbol-by-symbol completion

- [x] `LCM_list(v)`
    - `v`: Iterable
    - returns: `Integer` or `Any` (if generic LCM return something else, but typically Integer in this context)
- [x] `lcm(a, b=None)`
    - `a`, `b`: Any (elements with `.lcm` or coercible to Integer)
    - returns: Any (depends on input types)

## D. Dynamic/conditional behavior
- None.

## E. Internal consistency
- [x] Imports checked (`sage.rings.integer.Integer`).
- [x] Syntax verified.

## F. Review Gate
- [x] Verified.
