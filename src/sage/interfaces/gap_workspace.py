r"""
Support for (lib)GAP workspace files
"""

# ****************************************************************************
#       Copyright (C) 2017 Jeroen Demeyer <J.Demeyer@UGent.be>
#                     2019 Vincent Delecroix <vincent.delecroix@u-bordeaux.fr>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#                  https://www.gnu.org/licenses/
# ****************************************************************************

import os
import time
import hashlib
import shutil
import warnings
from sage.env import DOT_SAGE, HOSTNAME

#: Room that has to be free on the filesystem holding the workspace cache before
#: a workspace is written into it.  A saved workspace is GAP's whole memory
#: image -- 65 to 72 MB for the GAP this tree builds -- and GAP writes it in one
#: pass with nothing to report but ``Error, Cannot write to file`` when the
#: filesystem cannot take it (GAP 4.16 ``src/saveload.c``: that message is a
#: failed ``SyWrite``, after a successful open).  Below this much room the
#: workspaces of *other* GAP builds are removed first: they are caches, the
#: ``README.txt`` in the directory says they may be deleted, and keeping them
#: costs the call that needs the room.
GAP_WORKSPACE_MIN_FREE = 512 * 1024 * 1024


def _workspace_digest():
    r"""
    Return the digest that identifies the GAP the workspace belongs to.

    It covers the GAP version, its architecture and the roots it searches, but
    not the caller's own root ``$HOME/.gap/``: that says nothing about the GAP
    build, and hashing it gives every HOME -- hence every launcher that supplies
    one, and every ``DOT_SAGE`` moved with it -- a workspace of its own, at 65 to
    72 MB each for one and the same GAP.

    EXAMPLES::

        sage: from sage.interfaces.gap_workspace import _workspace_digest
        sage: d = _workspace_digest()
        sage: len(d) == 40
        True
    """
    from sage.libs.gap.util import kernel_info
    version, arch, roots = kernel_info()
    home = os.path.abspath(os.path.expanduser('~'))
    searched = [root for root in roots.split(';')
                if root and not _is_within(root, home)]
    data = ';'.join([version, arch] + searched)
    return hashlib.sha1(data.encode('utf-8')).hexdigest()


def _is_within(path, directory):
    r"""
    Return whether ``path`` is ``directory`` or below it.

    EXAMPLES::

        sage: from sage.interfaces.gap_workspace import _is_within
        sage: _is_within('/home/u/.gap/', '/home/u')
        True
        sage: _is_within('/home/uu/.gap/', '/home/u')
        False
    """
    path = os.path.abspath(path)
    return path == directory or path.startswith(directory + os.sep)


def _free_bytes(directory):
    r"""
    Return the free space on the filesystem holding ``directory``, or ``None``.

    EXAMPLES::

        sage: from sage.interfaces.gap_workspace import _free_bytes
        sage: _free_bytes('/') > 0
        True
        sage: _free_bytes('/nonexistent-sage-test-dir') is None
        True
    """
    try:
        return shutil.disk_usage(directory).free
    except OSError:
        return None


def _prune_workspace_dir(directory):
    r"""
    Remove the workspaces in ``directory`` that this GAP build cannot start from.

    Two of them are caches by declaration -- ``README.txt`` in the directory
    says so -- and both rules keep the directory bounded:

    * a workspace not used for a week is removed, as it always was;
    * when the filesystem is below :data:`GAP_WORKSPACE_MIN_FREE`, the
      workspaces of *other* GAP builds are removed as well, whoever wrote them.
      That is the room a fresh workspace needs, and it is found in the cache the
      caller was told to delete by hand otherwise.

    Workspaces of this build are kept: the digest in their name is
    :func:`_workspace_digest`.  What is removed is reported, not silent.

    EXAMPLES::

        sage: import os, tempfile, time, warnings
        sage: from sage.interfaces.gap_workspace import _prune_workspace_dir
        sage: with tempfile.TemporaryDirectory() as d:
        ....:     stale = os.path.join(d, 'gap-workspace-host-' + '0' * 40)
        ....:     open(stale, 'w').close()
        ....:     os.utime(stale, (time.time() - 10 * 86400,) * 2)
        ....:     with warnings.catch_warnings():
        ....:         warnings.simplefilter('ignore')
        ....:         _prune_workspace_dir(d)
        ....:     os.path.exists(stale)
        False
    """
    ours = _workspace_digest()
    free = _free_bytes(directory)
    short_of_room = free is not None and free < GAP_WORKSPACE_MIN_FREE
    now = time.time()
    removed = []
    for entry in sorted(os.listdir(directory)):
        if 'workspace' not in entry or entry.endswith(ours):
            continue
        path = os.path.join(directory, entry)
        try:
            stale = now - os.path.getatime(path) >= 604800    # one week
            if not (stale or short_of_room):
                continue
            size = os.path.getsize(path)
            os.unlink(path)
        except OSError:
            # It's not a problem if `path` doesn't exist, everything
            # else is an error.
            if os.path.exists(path):
                raise
        else:
            removed.append((entry, size))
    if removed:
        warnings.warn(
            "removed %d GAP workspace(s) from %s, %d bytes: %s%s"
            % (len(removed), directory, sum(size for _, size in removed),
               ', '.join(entry for entry, _ in removed),
               '' if short_of_room else ' (not used for a week)'),
            stacklevel=3)


def gap_workspace_file(system='gap', name='workspace', dir=None):
    r"""
    Return the filename for the GAP workspace.

    INPUT:

    - ``system`` -- the name of the system, either ``'gap'`` or
      ``'libgap'``

    - ``name`` -- the kind of workspace, usually ``'workspace'`` but
      the library interface also uses other files

    - ``dir`` -- the directory where the workspaces should be stored
      By default, this is ``DOT_SAGE/gap``

    EXAMPLES::

        sage: from sage.interfaces.gap_workspace import gap_workspace_file
        sage: gap_workspace_file("foo", "bar", "/somewhere")
        '/somewhere/foo-bar-...'

    TESTS::

        sage: from sage.env import DOT_SAGE
        sage: D = gap_workspace_file()
        sage: D.startswith(os.path.join(DOT_SAGE, "gap", "gap-workspace-"))
        True

    Check that the name generated is independent of the session::

        sage: from subprocess import Popen, PIPE
        sage: import sys
        sage: cmd = 'import sage.all, sage.interfaces.gap_workspace; print(sage.interfaces.gap_workspace.gap_workspace_file())'
        sage: name1 = Popen([sys.executable, '-c', cmd], stdout=PIPE).communicate()[0]
        sage: name2 = Popen([sys.executable, '-c', cmd], stdout=PIPE).communicate()[0]
        sage: assert name1 == name2
    """
    if dir is None:
        dir = os.path.join(DOT_SAGE, 'gap')

    h = _workspace_digest()
    return os.path.join(dir, f'{system}-{name}-{HOSTNAME}-{h}')


def prepare_workspace_dir(dir=None):
    r"""
    Create and clean up the directory for GAP workspaces.

    INPUT:

    - ``dir`` -- the directory where the workspaces should be stored
      By default, this is ``DOT_SAGE/gap``

    OUTPUT: the actual workspace directory

    EXAMPLES::

        sage: from sage.interfaces.gap_workspace import prepare_workspace_dir
        sage: prepare_workspace_dir()
        '.../gap'

    TESTS::

        sage: import tempfile
        sage: with tempfile.TemporaryDirectory() as d:
        ....:     prepare_workspace_dir(os.path.join(d, "new"))
        '.../new'
    """
    if dir is None:
        dir = os.path.join(DOT_SAGE, 'gap')

    # Make sure that the workspace directory exists
    try:
        os.makedirs(dir)
    except OSError:
        if not os.path.isdir(dir):
            raise
    else:
        # Directory was created, add a README file
        with open(os.path.join(dir, 'README.txt'), 'w') as f:
            f.write("It is OK to delete all these cache files.  They will be recreated as needed.\n")

    # Delete the workspaces this build cannot use, and make room when the
    # filesystem is short of it.  See _prune_workspace_dir for the two rules;
    # the directory's README.txt already says these files may be deleted.
    _prune_workspace_dir(dir)

    return dir
