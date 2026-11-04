# Supported harness route for the research suite, verified against the deployed runtime

Answers the handoff from research (deployment report `beea37a7a5`) about
`tests/constructions/test_set_ordering_and_mor_classification_construct.sage`.
**No runtime change is needed and none was made.** Everything below was measured
read-only: `bwrap` over the live rootfs mounted `ro`, with the consumer's own
directories bound in.

## The launcher

`/sage/.venv/bin/sage` is a 121-byte `#!/sage/.venv/bin/python` script and does not
accept `-m`; `sage -m pytest` fails with `unrecognized arguments: -m`. The harness
entry point is therefore the interpreter itself:

```
/sage/.venv/bin/python -m pytest ...
```

## The route that works

```
PYTHONPATH="<research>/.scratch/se-provider-6ad7a5ea/src:/home/ai-review-ci/tool-artifacts/pytest_plugins" \
  /sage/.venv/bin/python -m pytest \
    -o addopts= \
    -p qc_sage_session -p qc_xfail_issues -p qc_test_history -p qc_unique_inventory \
    --qc-history-dir <writable dir> \
    tests/constructions/test_set_ordering_and_mor_classification_construct.sage
```

Measured, from `/research` with `HOME` writable and `/reports` bound:

```
..                                                                       [100%]
2 passed in 0.35s
```

Collected first, to separate collection from execution:

```
tests/constructions/test_set_ordering_and_mor_classification_construct.sage::
  test_sets_ordered_refinements_are_the_owned_order_categories
tests/constructions/test_set_ordering_and_mor_classification_construct.sage::
  test_set_mor_knows_whether_its_endpoints_agree
2 tests collected in 0.43s
```

So the suite *does* run, and it passes, on the deployed runtime as it stands.

## Why it appeared unrunnable, exactly

`/research/pyproject.toml:65-70` sets

```
addopts = """
  --timeout=60 --timeout-method=signal
  --durations=0 --durations-min=0
  --junit-xml=tests/.report/junit.xml
  --report-log=tests/.report/run.jsonl
"""
```

and the deployed venv contains only `pytest 9.1.1`. Reproduced precisely:

```
ERROR: usage: python -m pytest [options] [file_or_dir] [...]
python -m pytest: error: unrecognized arguments: --timeout=60 --timeout-method=signal --report-log=tests/.report/run.jsonl
  inifile: /research/pyproject.toml
  rootdir: /research
```

**Missing installed prerequisites: `pytest-timeout` and `pytest-reportlog`, and nothing
else.** Both are optional under this route: `-o addopts=` drops the options that need
them, and the qc plugins supply the session and reporting instead.

## The qc plugins need no installation

`qc_sage_session`, `qc_xfail_issues`, `qc_test_history` and `qc_unique_inventory` are
plain modules at `ai-review-ci/tool-artifacts/pytest_plugins/`, not an installed
distribution — they load from `PYTHONPATH` and `-p`. None of the four exists in
`site-packages`, and none needs to. Loading them is enough; the only further
requirement is the one they state themselves:

```
ERROR: qc_test_history requires --qc-history-dir
```

with a writable directory supplied, they run.

## Provider pin: a discrepancy for research to reconcile, not a runtime defect

* The deployed runtime installs `/repos/sage-extensions` at **`7b222e86`**, which is
  what the runtime's own `verify` reports.
* The handoff names provider pin **`441519c5`**; that string appears in the research
  repository's own history (`.git/COMMIT_EDITMSG`, reflog) and its CI recipe, not in
  anything the runtime ships.
* The provider snapshot the process actually imports, `se-provider-6ad7a5ea`, lives in
  the research checkout's own `.scratch/` and enters through `PYTHONPATH` — a
  per-process bind, which is the supported mechanism.

Reconciling `441519c5` against `7b222e86` belongs to the research recipe's owner. The
shared runtime will not be pointed at an older extensions revision to match a consumer
recipe.

## Maintenance decision: none required

No boundary is needed for this suite. Nothing has to be installed into `/sage/.venv`
for it to run: the two pytest plugins are avoidable via `-o addopts=`, and the four qc
plugins load from `PYTHONPATH`. If research wants the pyproject `addopts` honoured as
written, that *would* require `pytest-timeout` and `pytest-reportlog` in the venv —
a runtime change at a maintenance boundary, and the only thing in this report that
is not already satisfiable per-process.

## `ModuleNotFoundError: hypothesis` — per-process route, verified

`hypothesis` is **declared** by research (`pyproject.toml:78`, `"hypothesis>=6.167.1"`)
and **absent** from the deployed venv. It needs no shared installation. Install into a
directory the consumer owns, then put it on `PYTHONPATH`:

```
UV_CACHE_DIR=/tmp/uvcache XDG_CACHE_HOME=/tmp \
UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_PYTHON_BIN_DIR=/usr/local/bin \
  uv pip install --python /sage/.venv/bin/python --target <consumer-owned dir> hypothesis
```

Measured:

```
landed: 4.3 MB in the target directory
hypothesis 6.170.14 from <target>/hypothesis/__init__.py    (>= 6.167.1, satisfied)
```

Two environment variables are required for `uv` to work against this image at all:
without `UV_CACHE_DIR`/`XDG_CACHE_HOME` it fails with
`Failed to initialize cache at /workspace/.../home/.cache/uv: Permission denied`, and
without `UV_PYTHON_INSTALL_DIR` it fails with
`Failed to discover managed Python installations`. Inside a container the image's own
`ENV` supplies these; a `bwrap` launch must pass them explicitly.

### Combined route, run against the real test

```
PYTHONPATH="<research>/.scratch/se-provider-6ad7a5ea/src:<ai-review-ci>/tool-artifacts/pytest_plugins:<hypothesis target>" \
  /sage/.venv/bin/python -m pytest -o addopts= \
    -p qc_sage_session -p qc_xfail_issues -p qc_test_history -p qc_unique_inventory \
    --qc-history-dir <writable dir> \
    tests/constructions/test_properties_construct.sage
```

```
15 failed in 310.44s (0:05:10)
```

The import error is gone — all fifteen tests collected and ran. That is the dependency
question answered, and it is **not** an acceptance: they fail, and the cause is a
provider API mismatch, not a missing package:

```
E   KeyError: 'order'                     sage/structure/category_object.pyx:858
    assert left.Aut().order() == factorial(n)
E   AttributeError: 'FixedIsoCategory_with_category' object has no attribute 'order'
```

The research snapshot (`se-provider-6ad7a5ea`) calls `order` on the automorphism
category; the deployed `sage-extensions` (`7b222e86`) does not provide it. This is the
same pin discrepancy recorded above — research's recipe references `441519c5`, the
runtime ships `7b222e86` — and it now has a concrete symptom. Resolving it belongs to
research's recipe and to `sage-extensions` (provider API), not to the shared runtime;
no consumer pin is changed here and nothing is installed into the venv.

## The fraction-field failure is a harness-contract defect, not a test defect

Reported: `qc_sage_session` raises a raw-Sage Integer conversion at
`ring_foundation.py:6384`, while `FractionFieldQuotients(ZZ)(2)` and `(ZZ(2))` succeed
outside pytest in the same runtime and binding.

### The contract, read from the plugin

`ai-review-ci/tool-artifacts/pytest_plugins/qc_sage_session.py` lowers a `.sage` file
with `sage.repl.preparse.preparse_file` and then executes it with

```python
module.__dict__["__builtins__"] = _sage_scope()      # = vars(builtins) + vars(sage.all_cmdline)
```

Two consequences, both measured:

1. **Literals are preparsed.** Inside the harness a literal `2` is a Sage `Integer`
   whose parent is `Integer Ring`:

   ```
   LITERAL type: Integer | parent: Integer Ring
   ZZ(2) type: Integer
   ```

2. **The names injected are `sage.all_cmdline`'s**, i.e. global Sage's, *not* the
   project's own session names. That is the defect. The provider distinguishes rings
   "of this session", and global Sage's `ZZ` is not one of them:

   ```
   K = FractionFieldQuotients(ZZ)
   TypeError: expected a ring of this session, but Integer Ring is not one
     se-provider-6ad7a5ea/src/sage_extensions/categories/rings/ring_foundation.py:7480
   ```

`FractionFieldQuotients` is not even in the injected scope (`NameError` until imported
explicitly), which is the same fact from the other side: the scope is Sage's, not the
project's.

### What this means for the report's symptoms

The `6384` frame is the `__contains__` fall-back `return value in self._engine`; the
Integer it cannot convert is the preparsed literal, and the ring it was called on came
from a session that the provider does not consider its own. Outside pytest the same
expression uses the project's own preamble bindings, so both `2` and `ZZ(2)` are owned
rings' elements and it passes.

### Conclusion

* The **test is correct** and should stay unchanged; it is entitled to the project's
  session bindings.
* The **harness is at fault**: `qc_sage_session` binds `sage.all_cmdline`, which
  substitutes global Sage names for the project's owned ones. A `.sage` test run under
  it is not the same session the project's own runner creates.
* This is **not** a runtime defect and nothing in the shared runtime was changed.

The fix belongs to `ai-review-ci`'s plugin: execute the lowered module in the project's
own session namespace (whatever the project's preamble/runner installs) rather than
`vars(sage.all_cmdline)`, or make that scope overridable per project. Reported, not
worked around: no alternate path, no plugin copy, no test edit.
