# Checklist for `sage.arith.all`

## A. Skeleton provenance
- [x] Stubgen command used: `stubgen --parse-only sage/arith/all.py -o ../typings`
- [x] Stubgen log file path: `tools/typing/logs/sage.arith.all.log`

## B. Export surface
- [x] Explicit re-exports from `sage.arith.misc`.
- [x] Explicit re-exports from `sage.arith.functions` (`lcm`, `LCM`).
- [x] Explicit re-exports from `sage.arith.srange` (`xsrange`, `srange`, etc.).
- [x] `sxrange` alias.
- [x] `σ` alias.

## C. Symbol-by-symbol completion
- This module is purely re-exports.

## D. Dynamic/conditional behavior
- None.

## E. Internal consistency
- [x] Verified imports.
- [x] Verified syntax.

## F. Review Gate
- [x] Verified.
