# Checklist for `sage.misc.html`

## A. Skeleton provenance
- [x] Stubgen command used: `stubgen --parse-only sage/misc/html.py -o ../typings`
- [x] Stubgen log file path: `tools/typing/logs/sage.misc.html.log` (implicit)

## B. Export surface
- [x] `HtmlFragment`
- [x] `math_parse`
- [x] `MathJaxExpr`
- [x] `MathJax`
- [x] `HTMLFragmentFactory`
- [x] `html` (instance of `HTMLFragmentFactory`)
- [x] `pretty_print_default`

## C. Symbol-by-symbol completion

- [x] `HtmlFragment` (class)
- [x] `math_parse(s)` -> `HtmlFragment`
- [x] `MathJaxExpr` (class)
    - `__init__`
    - `__add__`
    - `__radd__`
- [x] `MathJax` (class)
    - `__call__`
    - `eval`
- [x] `HTMLFragmentFactory` (class)
    - `__call__`
    - `eval`
    - `iframe`
- [x] `html` (instance)
- [x] `pretty_print_default`

## D. Dynamic/conditional behavior
- None.

## E. Internal consistency
- [x] Imports checked.
- [x] Syntax verified.

## F. Review Gate
- [x] Verified.
