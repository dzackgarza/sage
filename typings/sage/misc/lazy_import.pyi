"""
Lazy imports

This module allows one to lazily import objects into a namespace,
where the actual import is delayed until the object is actually called
or inspected. This is useful for modules that are expensive to import
or may cause circular references, though there is some overhead in its
use.

EXAMPLES::

    sage: lazy_import('sage.rings.integer_ring', 'ZZ')
    sage: type(ZZ)
    <class 'sage.misc.lazy_import.LazyImport'>
    sage: ZZ(4.0)
    4

By default, a warning is issued if a lazy import module is resolved
during Sage's startup. In case a lazy import's sole purpose is to
break a circular reference and it is known to be resolved at startup
time, one can use the ``at_startup`` option::

    sage: lazy_import('sage.rings.integer_ring', 'ZZ', at_startup=True)

This option can also be used as an intermediate step toward not
importing by default a module that is used in several places, some of
which can already afford to lazy import the module but not all.

A lazy import that is marked as "at_startup" will print a message if
it is actually resolved after the startup, so that the developer knows
that (s)he can remove the flag::

    sage: ZZ
    doctest:warning...
    UserWarning: Option ``at_startup=True`` for lazy import ZZ not needed anymore
    Integer Ring

.. WARNING::

    After the first usage, the imported object is directly injected into the
    namespace; however, before that, the :class:`LazyImport` object
    is not exactly equivalent to the actual imported object. For example::

        sage: from sage.misc.lazy_import import LazyImport
        sage: my_qqbar = LazyImport('sage.rings.qqbar', 'QQbar')
        sage: my_qqbar(5) == QQbar(5)  # good
        True
        sage: isinstance(QQbar, Parent)
        True
        sage: isinstance(my_qqbar, Parent)  # fails!
        False

    To avoid this issue, you may execute the import inside the function instead.

.. SEEALSO:: :func:`lazy_import`, :class:`LazyImport`

AUTHOR:

 - Robert Bradshaw
"""
from __future__ import annotations

import cython


@cython.final
class LazyImport:
    """
    EXAMPLES::

        sage: from sage.misc.lazy_import import LazyImport
        sage: my_integer = LazyImport('sage.rings.integer', 'Integer')
        sage: my_integer(4)
        4
        sage: my_integer('101', base=2)
        5
        sage: my_integer(3/2)
        Traceback (most recent call last):
        ...
        TypeError: no conversion of this rational to integer
    """

    def __init__(self, module, name, as_name=None, at_startup=False, namespace=None, deprecation=None, feature=None):
        """
        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: type(lazy_ZZ)
            <class 'sage.misc.lazy_import.LazyImport'>
            sage: lazy_ZZ._get_object() is ZZ
            True
            sage: type(lazy_ZZ)
            <class 'sage.misc.lazy_import.LazyImport'>
        """

    def _instancedoc_(self):
        """
        Return the docstring of the wrapped object for introspection.

        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: my_isprime = LazyImport('sage.arith.misc', 'is_prime')
            sage: my_isprime.__doc__ is is_prime.__doc__
            True

        TESTS:

        Check that :issue:`19475` is fixed::

            sage: 'A subset of the real line' in RealSet.__doc__
            True
        """

    def _sage_src_(self):
        """
        Return the source of the wrapped object for introspection.

        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: my_isprime = LazyImport('sage.arith.misc', 'is_prime')
            sage: 'def is_prime(' in my_isprime._sage_src_()
            True
        """

    def _sage_argspec_(self):
        """
        Return the argspec of the wrapped object for introspection.

        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: rm = LazyImport('sage.matrix.special', 'random_matrix')
            sage: rm._sage_argspec_()                                                   # needs sage.modules
            FullArgSpec(args=['ring', 'nrows', 'ncols', 'algorithm', 'implementation'],
                        varargs='args', varkw='kwds', defaults=(None, 'randomize', None),
                        kwonlyargs=[], kwonlydefaults=None, annotations={})
        """

    def __getattr__(self, attr):
        """
        Attribute lookup on ``self`` defers to attribute lookup on the
        wrapped object.

        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: my_integer = LazyImport('sage.rings.integer', 'Integer')
            sage: my_integer.sqrt is Integer.sqrt
            True
        """

    def __dir__(self):
        """
        Tab completion on ``self`` defers to completion on the wrapped
        object.

        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: dir(lazy_ZZ) == dir(ZZ)
            True
        """

    def __call__(self, *args, **kwds):
        """
        Calling ``self`` calls the wrapped object.

        EXAMPLES::

            sage: from sage.misc.lazy_import import LazyImport
            sage: my_isprime = LazyImport('sage.arith.misc', 'is_prime')
            sage: is_prime(12) == my_isprime(12)
            True
            sage: is_prime(13) == my_isprime(13)
            True
        """

    def __repr__(self):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: repr(lazy_ZZ) == repr(ZZ)
            True
        """

    def __str__(self):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: str(lazy_ZZ) == str(ZZ)
            True
        """

    def __bool__(self):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: bool(lazy_ZZ) == bool(ZZ)
            True
        """

    def __hash__(self):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: hash(lazy_ZZ) == hash(ZZ)
            True
        """

    def __richcmp__(left, right, op: int):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: lazy_ZZ = LazyImport('sage.rings.integer_ring', 'ZZ')
            sage: lazy_ZZ == ZZ
            True
            sage: lazy_ZZ == RR
            False
        """

    def __len__(self):
        """
        TESTS::

            sage: lazy_import('sys', 'version_info')
            sage: type(version_info)
            <class 'sage.misc.lazy_import.LazyImport'>
            sage: len(version_info)
            5
        """

    def __get__(self, instance, owner):
        """
        EXAMPLES:

        Here we show how to take a function in a module, and lazy
        import it as a method of a class. For the sake of this
        example, we add manually a function in :mod:`sage.all`::

            sage: def my_method(self): return self
            sage: import sage.all
            sage: sage.all.my_method = my_method

        Now we lazy import it as a method of a new class ``Foo``::

            sage: from sage.misc.lazy_import import LazyImport
            sage: class Foo():
            ....:     my_method = LazyImport('sage.all', 'my_method')

        Now we can use it as a usual method::

            sage: Foo().my_method()
            <__main__.Foo object at ...>
            sage: Foo.my_method
            <function my_method at 0x...>
            sage: Foo().my_method
            <bound method my_method of <__main__.Foo object at ...>>

        When a :class:`LazyImport` method is a method (or attribute)
        of a class, then extra work must be done to replace this
        :class:`LazyImport` object with the actual object. See the
        documentation of :meth:`_get_object` for an explanation of
        this.

        .. NOTE::

           For a :class:`LazyImport` object that appears in a class
           namespace, we need to do something special. Indeed, the
           class namespace dictionary at the time of the class
           definition is not the one that actually gets used. Thus,
           ``__get__`` needs to manually modify the class dict::

               sage: class Foo():
               ....:     lazy_import('sage.plot.plot', 'plot')
               sage: class Bar(Foo):
               ....:     pass
               sage: type(Foo.__dict__['plot'])
               <class 'sage.misc.lazy_import.LazyImport'>

           We access the ``plot`` method::

               sage: Bar.plot                                                           # needs sage.plot
               <function plot at 0x...>

           Now ``plot`` has been replaced in the dictionary of ``Foo``::

               sage: type(Foo.__dict__['plot'])                                         # needs sage.plot
               <... 'function'>
        """

    def __getitem__(self, key):
        """
        TESTS::

            sage: import sys
            sage: py_version = sys.version_info[0]
            sage: lazy_import('sys', 'version_info')
            sage: version_info[0] == py_version
            True
        """

    def __setitem__(self, key, value):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: import sage.all
            sage: sage.all.foo = list(range(10))
            sage: lazy_foo = LazyImport('sage.all', 'foo')
            sage: lazy_foo[1] = 100
            sage: print(lazy_foo)
            [0, 100, 2, 3, 4, 5, 6, 7, 8, 9]
            sage: sage.all.foo
            [0, 100, 2, 3, 4, 5, 6, 7, 8, 9]
        """

    def __delitem__(self, key):
        """
        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: import sage.all
            sage: sage.all.foo = list(range(10))
            sage: lazy_foo = LazyImport('sage.all', 'foo')
            sage: del lazy_foo[1]
            sage: print(lazy_foo)
            [0, 2, 3, 4, 5, 6, 7, 8, 9]
            sage: print(sage.all.foo)
            [0, 2, 3, 4, 5, 6, 7, 8, 9]
        """

    def __iter__(self):
        """
        TESTS::

            sage: lazy_import('sys', 'version_info')
            sage: iter(version_info)
            <...iterator object at ...>
        """

    def __contains__(self, item):
        """
        TESTS::

            sage: import sys
            sage: py_version = sys.version_info[0]
            sage: lazy_import('sys', 'version_info')
            sage: py_version in version_info
            True

            sage: lazy_import('sys', 'version_info')
            sage: 2000 not in version_info
            True
        """

    def __add__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo + 1
            11
        """

    def __sub__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo - 1
            9
        """

    def __mul__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo * 2
            20
        """

    def __matmul__(left, right):
        """
        TESTS::

            sage: # needs sympy
            sage: from sympy import Matrix
            sage: import sage.all
            sage: sage.all.foo = Matrix([[1,1], [0,1]])
            sage: lazy_import('sage.all', 'foo')
            sage: foo.__matmul__(foo)
            Matrix([
            [1, 2],
            [0, 1]])
        """

    def __floordiv__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo  // 3
            3
        """

    def __truediv__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: operator.truediv(foo, 3)
            10/3
        """

    def __pow__(left, right, mod):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo ** 2
            100
        """

    def __mod__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo % 7
            3
        """

    def __lshift__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo << 3
            80
        """

    def __rshift__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo >> 2
            2
        """

    def __and__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo & 7
            2
        """

    def __or__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo | 7
            15
        """

    def __xor__(left, right):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: foo ^^ 7
            13
        """

    def __neg__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: -foo
            -10
        """

    def __pos__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: +foo
            10
        """

    def __abs__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = -1000
            sage: lazy_import('sage.all', 'foo')
            sage: abs(foo)
            1000
        """

    def __invert__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: ~foo
            1/10
        """

    def __complex__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: complex(foo)
            (10+0j)
        """

    def __int__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: int(foo)
            10
        """

    def __float__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: float(foo)
            10.0
        """

    def __oct__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: oct(foo)
            '0o12'
        """

    def __hex__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: hex(foo)
            '0xa'
        """

    def __index__(self):
        """
        TESTS::

            sage: import sage.all
            sage: sage.all.foo = 10
            sage: lazy_import('sage.all', 'foo')
            sage: list(range(100))[foo]
            10
        """

    def __copy__(self):
        """
        Support ``copy()``.

        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: import sage.all
            sage: sage.all.foo = [[1,2], 3]
            sage: lazy_foo = LazyImport('sage.all', 'foo')
            sage: a = copy(lazy_foo)
            sage: a is sage.all.foo        # copy
            False
            sage: a[0] is sage.all.foo[0]  # copy but not deep
            True
            sage: type(lazy_foo) is LazyImport
            True
        """

    def __deepcopy__(self, memo=None):
        """
        Support ``copy()``.

        TESTS::

            sage: from sage.misc.lazy_import import LazyImport
            sage: import sage.all
            sage: sage.all.foo = [[1,2], 3]
            sage: lazy_foo = LazyImport('sage.all', 'foo')
            sage: a = deepcopy(lazy_foo)
            sage: a is sage.all.foo        # copy
            False
            sage: a[0] is sage.all.foo[0]  # deep copy
            False
            sage: type(lazy_foo) is LazyImport
            True
        """

    def __instancecheck__(self, x):
        """
        Support ``isinstance()``.

        EXAMPLES::

            sage: lazy_import('sage.rings.rational_field', 'RationalField')
            sage: isinstance(QQ, RationalField)
            True

        No object is an instance of a class that cannot be imported::

            sage: lazy_import('sage.xxxxx_does_not_exist', 'DoesNotExist')
            sage: isinstance(QQ, DoesNotExist)
            False
        """

    def __subclasscheck__(self, x):
        """
        Support ``issubclass()``.

        EXAMPLES::

            sage: lazy_import('sage.structure.parent', 'Parent')
            sage: issubclass(RationalField, Parent)
            True

        No class is a subclass of a class that cannot be imported::

            sage: lazy_import('sage.xxxxx_does_not_exist', 'DoesNotExist')
            sage: issubclass(RationalField, DoesNotExist)
            False
        """
star_imports = None

def finish_startup():
    """
    Finish the startup phase.

    This function must be called exactly once at the end of the Sage
    import process (:mod:`~sage.all`).

    TESTS::

        sage: from sage.misc.lazy_import import finish_startup
        sage: finish_startup()
        Traceback (most recent call last):
        ...
        AssertionError: finish_startup() must be called exactly once
    """

def ensure_startup_finished():
    """
    Make sure that the startup phase is finished.

    In contrast to :func:`finish_startup`, this function can
    be called repeatedly.

    TESTS::

        sage: from sage.misc.lazy_import import ensure_startup_finished
        sage: ensure_startup_finished()
    """

def is_during_startup() -> bool:
    """
    Return whether Sage is currently starting up.

    OUTPUT: boolean

    TESTS::

        sage: from sage.misc.lazy_import import is_during_startup
        sage: is_during_startup()
        False
    """

def test_fake_startup():
    """
    For testing purposes only.

    Switch the startup lazy import guard back on.

    EXAMPLES::

        sage: sage.misc.lazy_import.test_fake_startup()
        sage: lazy_import('sage.rings.integer_ring', 'ZZ', 'my_ZZ')
        sage: my_ZZ(123)
        doctest:warning...
        UserWarning: Resolving lazy import ZZ during startup
        123
        sage: sage.misc.lazy_import.finish_startup()
    """

def lazy_import(module, names, as_=None, *, at_startup=False, namespace=None, deprecation=None, feature=None):
    """
    Create a lazy import object and inject it into the caller's global
    namespace. For the purposes of introspection and calling, this is
    like performing a lazy "from module import name" where the import
    is delayed until the object actually is used or inspected.

    INPUT:

    - ``module`` -- string representing the module to import

    - ``names`` -- string or list of strings representing the names to
      import from module

    - ``as_`` -- (optional) a string or list of strings representing the
      names of the objects in the importing module. This is analogous to
      ``from ... import ... as ...``.

    - ``at_startup`` -- boolean (default: ``False``);
      whether the lazy import is supposed to be resolved at startup time

    - ``namespace`` -- the namespace where importing the names; by default,
      import the names to current namespace

    - ``deprecation`` -- (optional) if not ``None``, a deprecation warning
      will be issued when the object is actually imported;
      ``deprecation`` should be either a trac number (integer) or a
      pair ``(issue_number, message)``

    - ``feature`` -- a python module (optional), if it cannot be imported
      an appropriate error is raised

    .. SEEALSO:: :mod:`sage.misc.lazy_import`, :class:`LazyImport`

    EXAMPLES::

        sage: lazy_import('sage.rings.integer_ring', 'ZZ')
        sage: type(ZZ)
        <class 'sage.misc.lazy_import.LazyImport'>
        sage: ZZ(4.0)
        4
        sage: lazy_import('sage.rings.real_double', 'RDF', 'my_RDF')
        sage: my_RDF._get_object() is RDF
        True
        sage: my_RDF(1/2)
        0.5

        sage: lazy_import('sage.rings.rational_field', ['QQ', 'frac'], ['my_QQ', 'my_frac'])
        sage: my_QQ._get_object() is QQ
        True
        sage: my_frac._get_object() is sage.rings.rational_field.frac
        True

    Upon the first use, the object is injected directly into
    the calling namespace::

        sage: lazy_import('sage.rings.integer_ring', 'ZZ', 'my_ZZ')
        sage: my_ZZ is ZZ
        False
        sage: my_ZZ(37)
        37
        sage: my_ZZ is ZZ
        True

    We check that :func:`lazy_import` also works for methods::

        sage: class Foo():
        ....:     lazy_import('sage.plot.plot', 'plot')
        sage: class Bar(Foo):
        ....:     pass
        sage: type(Foo.__dict__['plot'])
        <class 'sage.misc.lazy_import.LazyImport'>
        sage: 'EXAMPLES' in Bar.plot.__doc__                                            # needs sage.plot
        True
        sage: type(Foo.__dict__['plot'])                                                # needs sage.plot
        <... 'function'>

    If deprecated then a deprecation warning is issued::

        sage: lazy_import('sage.rings.padics.factory', 'Qp', 'my_Qp',
        ....:             deprecation=14275)
        sage: my_Qp(5)                                                                  # needs sage.rings.padics
        doctest:...: DeprecationWarning:
        Importing my_Qp from here is deprecated;
        please use "from sage.rings.padics.factory import Qp as my_Qp" instead.
        See https://github.com/sagemath/sage/issues/14275 for details.
        5-adic Field with capped relative precision 20

    An example of deprecation with a message::

        sage: lazy_import('sage.rings.padics.factory', 'Qp', 'my_Qp_msg',
        ....:             deprecation=(14275, "This is an example."))
        sage: my_Qp_msg(5)                                                              # needs sage.rings.padics
        doctest:...: DeprecationWarning: This is an example.
        See https://github.com/sagemath/sage/issues/14275 for details.
        5-adic Field with capped relative precision 20

    An example of an import relying on a feature::

        sage: from sage.features import PythonModule
        sage: lazy_import('ppl', 'equation',
        ....:             feature=PythonModule('ppl', spkg='pplpy', type='standard'))
        sage: equation                                                                  # needs pplpy
        <cyfunction equation at ...>
        sage: lazy_import('PyNormaliz', 'NmzListConeProperties',
        ....:             feature=PythonModule('PyNormaliz', spkg='pynormaliz'))
        sage: NmzListConeProperties                             # optional - pynormaliz
        <built-in function NmzListConeProperties>
        sage: lazy_import('foo', 'not_there',
        ....:             feature=PythonModule('foo', spkg='non-existing-package'))
        sage: not_there
        Failed lazy import:
        foo is not available.
        Importing not_there failed: No module named 'foo'...
        No equivalent system packages for ... are known to Sage...
    """

def save_cache_file():
    """
    Used to save the cached * import names.

    TESTS::

        sage: import sage.misc.lazy_import
        sage: sage.misc.lazy_import.save_cache_file()
    """

def get_star_imports(module_name):
    """
    Lookup the list of names in a module that would be imported with "import \\*"
    either via a cache or actually importing.

    EXAMPLES::

        sage: from sage.misc.lazy_import import get_star_imports
        sage: 'get_star_imports' in get_star_imports('sage.misc.lazy_import')
        True
        sage: 'EllipticCurve' in get_star_imports('sage.schemes.all')                   # needs sage.schemes
        True

    TESTS::

        sage: import os, tempfile
        sage: fd, cache_file = tempfile.mkstemp()
        sage: os.write(fd, b'invalid')
        7
        sage: os.close(fd)
        sage: import sage.misc.lazy_import as lazy
        sage: import sage.misc.lazy_import_cache as cache
        sage: cache.get_cache_file = (lambda: cache_file)
        sage: lazy.star_imports = None
        sage: lazy.get_star_imports('sage.schemes.all')                                 # needs sage.schemes
        doctest:...: UserWarning: star_imports cache is corrupted
        [...]
        sage: os.remove(cache_file)
    """

def attributes(a):
    """
    Return the private attributes of a :class:`LazyImport` object in a dictionary.

    This is for debugging and doctesting purposes only.

    EXAMPLES::

        sage: from sage.misc.lazy_import import attributes
        sage: lazy_import("sage.structure.unique_representation", "foo")
        sage: attributes(foo)['_namespace'] is globals()
        True
        sage: D = attributes(foo)
        sage: del D['_namespace']
        sage: D
        {'_as_name': 'foo',
         '_at_startup': False,
         '_deprecation': None,
         '_module': 'sage.structure.unique_representation',
         '_name': 'foo',
         '_object': None}
    """

def clean_namespace(namespace=None):
    """
    Adjust :class:`LazyImport` bindings in given namespace to refer to this actual namespace.

    When :class:`LazyImport` objects are imported into other namespaces via normal ``import``
    instructions, the data stored on a :class:`LazyImport` object that helps it to adjust the
    binding in the namespace to the actual imported object upon access is not adjusted.
    This routine fixes that.

    INPUT:

    - ``namespace`` -- the namespace where importing the names; by default,
      import the names to current namespace

    EXAMPLES::

        sage: # needs sage.symbolic
        sage: from sage.misc.lazy_import import attributes, clean_namespace
        sage: from sage.misc.functional import CDF as C
        sage: attributes(C)['_as_name']
        'CDF'
        sage: attributes(C)['_namespace'] is sage.misc.functional.__dict__
        True
        sage: clean_namespace(globals())
        sage: attributes(C)['_as_name']
        'C'
        sage: attributes(C)['_namespace'] is globals()
        True
    """

# This file was generated by stubgen-pyx v0.2.2 from src/sage/misc/lazy_import.pyx