# Checklist for sage.rings.complex_double

## A. Skeleton provenance

- [x] stubgen command used: `stubgen --module sage.rings.complex_double`
- [x] stubgen log file path: `tools/typing/logs/sage.rings.complex_double.log`
- [x] any stubgen parsing failures/warnings: None reported.

## B. Export surface

- [x] export determination method: Analyzed `.pyx` file and imports.
- [x] final list of exported names represented in the stub:
  - `ComplexDoubleField_class`
  - `ComplexDoubleElement`
  - `FloatToCDF`
  - `ComplexToCDF`
  - `CDF`, `_CDF`
  - `ComplexDoubleField`
  - `is_ComplexDoubleElement`

## C. Symbol-by-symbol completion

- [x] `ComplexDoubleField_class`:
  - Methods and signatures verified against source.
  - `random_element` types.
  - `to_prec` returns.
  - `pi`, `zeta`, `gen`.
- [x] `ComplexDoubleElement`:
  - Inherits `FieldElement`.
  - Properties: `real_part`, `imag_part`.
  - Arithmetic methods (`_add_`, etc.).
  - Math methods (`sqrt`, `exp`, `log`, trig, hyperbolic).
  - Conversions (`__float__`, `__complex__`, `__mpc__`).
  - Overloads for `sqrt`, `nth_root`.
- [x] Morphisms: `FloatToCDF`, `ComplexToCDF`.
- [x] Global functions.

## D. Dynamic/conditional behavior

- [x] `ComplexDoubleFieldABC` mocked as `Any`.
- [x] Imports for `RealDoubleElement` and `Integer` handled.

## E. Internal consistency

- [x] stub parses.
- [x] imports: `gmpy2` required.

## F. Review gate

- [ ] reviewer sign-off recorded.
