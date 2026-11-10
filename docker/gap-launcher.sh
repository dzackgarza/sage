#!/bin/sh
# The image's GAP, found however this filesystem is run.
#
# Sage starts GAP twice over: `sage.interfaces.gap` runs the bare command `gap`
# and gives it `-L <workspace>`, and `sage.libs.gap.util.kernel_info()` runs the
# same bare command to learn the version, the architecture and the roots the
# workspace is hashed from.  Both resolve it through PATH, so a process whose
# environment did not come from this image -- PRoot over the unpacked
# filesystem, a bare exec, an entrypoint that rebuilds the environment -- has no
# `gap` at all, and `from sage.interfaces.gap import gap` stops with
# `FileNotFoundError: 'gap'` before any mathematics runs (sage#19).  A PATH that
# does find one under /usr/bin would be worse: that is a distribution GAP, and
# libgap.so.11 reading GAP 4.14's library is a segfault, not an exception
# (sage#11).
#
# /usr/local/bin is where a launcher's inherited PATH looks; $SAGE_LOCAL/bin is
# where this image's GAP is.  Exec rather than link: GAP derives the roots it
# searches from the program it was started as, and here argv[0] is the image's
# own binary -- measured with this wrapper bound over /usr/local/bin/gap, where
# kernel_info() reported 4.16.1 with /sage/.venv/lib/gap/ and
# /sage/.venv/share/gap/ among the roots.
exec /sage/.venv/bin/gap "$@"
