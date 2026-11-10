r"""
What GAP says about itself: its version, its architecture, and its root paths.

``sage.ext_data.gap.kernel-info.g`` runs before GAP's library is loaded -- that
is what makes this cheap -- and prints those three records on three lines.  GAP
breaks a printed line that reaches its line width and marks the break with a
backslash, and the roots record begins with ``$HOME/.gap/``, so a long enough
``HOME`` used to split it: ``sage.interfaces.gap`` then failed at import with
``ValueError: too many values to unpack (expected 3)`` (sage#20).  The records
are read across the breaks, so the length of ``HOME`` cannot decide whether the
interface imports.

The public name is still ``sage.libs.gap.util.kernel_info``; that module imports
this one.
"""

import subprocess
from importlib.resources import files

from sage.misc.cachefunc import cached_function


def parse_kernel_info(stdout):
    r"""
    Return the three records ``kernel-info.g`` prints, read across GAP's breaks.

    GAP ends a line it broke with a backslash, and the break falls between two
    characters of the record, so removing the backslash and the newline after it
    restores the record whatever width GAP printed at.

    INPUT:

    - ``stdout`` -- what ``gap --systemfile kernel-info.g`` printed

    OUTPUT:

    A tuple ``(version, architecture, root paths)``.

    EXAMPLES::

        sage: from sage.libs.gap.kernel_info import parse_kernel_info
        sage: parse_kernel_info("4.16.1\nx86_64-pc-linux-gnu-default64-kv11\n/u/.gap/;/sage/.venv/lib/gap/\n")
        ('4.16.1', 'x86_64-pc-linux-gnu-default64-kv11', '/u/.gap/;/sage/.venv/lib/gap/')

    A roots record that GAP broke at its line width is one record again::

        sage: broken = "4.16.1\nx86_64\n/home/a-long-\\" + "\n" + "name/.gap/;/sage/.venv/lib/gap/\n"
        sage: parse_kernel_info(broken)[2]
        '/home/a-long-name/.gap/;/sage/.venv/lib/gap/'

    A shape that is not the three records is named rather than unpacked into a
    bare ``too many values``::

        sage: parse_kernel_info("4.16.1\nx86_64\n/a/\n/b/\n")
        Traceback (most recent call last):
        ...
        ValueError: GAP printed 4 records where kernel-info.g prints three (version, architecture, root paths): '4.16.1\nx86_64\n/a/\n/b/\n'
    """
    records = stdout.replace("\\\n", "").strip().split("\n")
    if len(records) != 3:
        raise ValueError(
            "GAP printed %d records where kernel-info.g prints three "
            "(version, architecture, root paths): %r" % (len(records), stdout))
    return tuple(records)


@cached_function
def kernel_info() -> tuple[str, str, str]:
    r"""
    Return the GAP version, architecture, and root paths in a tuple.

    The first two are used as cache keys to invalidate old workspaces
    in ``sage.interfaces.gap_workspace.gap_workspace_file``. The
    root paths are required to initialize libgap. In the past we
    computed the root paths at build-time, but that may not work if
    (say) the build and target hosts have different libdirs.

    This is fast enough that it should suffice until a more reliable
    method is available (GAP Github issue 6252).

    OUTPUT:

    A tuple containing three strings:

    1. The GAP version
    2. The GAP architecture
    3. A semicolon-delimited list of GAP's RootPaths

    TESTS:

    Confirm the claims of our ``OUTPUT`` block::

        sage: from sage.libs.gap.util import kernel_info
        sage: ki = kernel_info()
        sage: isinstance(ki, tuple)
        True
        sage: len(ki) == 3
        True
        sage: all( isinstance(p, str) for p in ki )
        True

    The roots record is read whether or not GAP broke it: no length of ``HOME``
    can decide whether this returns three records (sage#20).
    """
    systemfile = files("sage").joinpath("ext_data/gap/kernel-info.g")
    result = subprocess.run(["gap", "--systemfile", systemfile],
                            capture_output=True,
                            check=True,
                            text=True)
    return parse_kernel_info(result.stdout)
