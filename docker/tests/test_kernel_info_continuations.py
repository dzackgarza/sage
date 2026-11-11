"""kernel_info() reads GAP's roots record across the breaks GAP prints (sage#20).

GAP ends a printed line that reaches its line width with a backslash and breaks
it there, and the roots record begins with ``$HOME/.gap/``, so a long enough
``HOME`` used to split it: ``sage.interfaces.gap`` then failed at import with
``ValueError: too many values to unpack (expected 3)`` (sage#20). The fix
(``src/sage/libs/gap/kernel_info.py``, landed at 2e8306e94cca) joins the
continuation lines, so the length of ``HOME`` cannot decide whether the
interface imports.

The failure on the unfixed code, recorded before the fix was bound over it:
the launcher's own GAP, under a HOME grown past the line width, printed the
roots record in two lines and the parser died at
``ValueError: too many values to unpack (expected 3)``. This test is the
regression: the parser joins the break and still returns three records.
"""

import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
KERNEL_INFO = REPOSITORY / "src" / "sage" / "libs" / "gap" / "kernel_info.py"


def test_kernel_info_joins_gaps_continuation_lines():
    """A roots record GAP broke at its line width is one record again."""
    # The break GAP prints: a backslash at the width, the record continued on
    # the next line. The roots record begins with $HOME/.gap/, so a HOME long
    # enough reaches the width.
    broken = "4.16.1\nx86_64-pc-linux-gnu-default64-kv11\n" \
              + "/workspace/nucleus/work/home/pad" * 1 + "\\" + "\n" \
              + ".gap/;/sage/.venv/lib/gap/;/sage/.venv/share/gap/\n"
    sys.path.insert(0, str(KERNEL_INFO.parent))
    import kernel_info
    version, architecture, roots = kernel_info.parse_kernel_info(broken)
    assert version == "4.16.1"
    assert architecture == "x86_64-pc-linux-gnu-default64-kv11"
    assert roots.startswith("/workspace/nucleus/work/home/pad")
    assert "/sage/.venv/lib/gap/" in roots
    assert "/sage/.venv/share/gap/" in roots
