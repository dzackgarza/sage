# Checklist for sage.rings.real_double

## A. Skeleton provenance

- [x] stubgen command used: `stubgen --module sage.rings.real_double` (via batch script)
- [x] stubgen log file path: `tools/typing/logs/sage.rings.real_double.log`
- [x] any stubgen parsing failures/warnings: None reported.

## B. Export surface

- [x] export determination method: Analyzed `.pyx` file and imports.
- [x] final list of exported names represented in the stub:
  - `RealDoubleField_class`
  - `RealDoubleElement`
  - `ToRDF`
  - `RDF`
  - `_RDF`
  - `RealDoubleField`
  - `is_RealDoubleElement`

## C. Symbol-by-symbol completion

- [x] `RealDoubleField_class`:
  - Inherits from `RealDoubleFieldABC` (placeholder for `sage.rings.abc.RealDoubleField`).
  - Implements standard field methods (`__init__`, `gen`, `random_element`, `characteristic`, etc.).
  - `pi`, `euler_constant`, `log2`, `NaN` return `RealDoubleElement`.
  - `to_prec` returns `RealDoubleField` or `RealField` (mpfr).
  - `complex_field`, `algebraic_closure` return `CDF`.
- [x] `RealDoubleElement`:
  - Inherits from `FieldElement`.
  - Implements arithmetic (`_add_`, `_sub_`, `_mul_`, `_div_`, `__neg__`, `__invert__`).
  - Implements conversions (`__float__`, `__int__`, `__complex__`, `_integer_`, `__mpfr__`).
  - Implements math functions (`sqrt`, `log2` via field, `exp`?, `sin`? - these seem handled via coercion or symbolic or not present on element directly? Ah, `sqrt` is there. `log` is `log2` on parent. `RealDoubleElement` has `sqrt`, `cube_root`, `agm`).
  - `sign_mantissa_exponent`, `as_integer_ratio`.
  - `floor`, `ceil`, `trunc`, `round` return `Integer`.
- [x] `ToRDF`:
  - Inherits from `Morphism`.
  - `_call_` returns `RealDoubleElement`.
- [x] Global functions:
  - `RealDoubleField()` returns singleton.
  - `is_RealDoubleElement` (deprecated) returns `bool`.

## D. Dynamic/conditional behavior

- None identified that affects typing significantly (imports handled).

## E. Internal consistency

- [x] stub parses.
- [x] imports: `Integer` from `sage.rings.integer`, `FieldElement` from `sage.structure.element`.

## F. Review gate

- [ ] reviewer sign-off recorded.
