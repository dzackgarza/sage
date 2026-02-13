"""
Rational Numbers

AUTHORS:

- William Stein (2005): first version

- William Stein (2006-02-22): floor and ceil (pure fast GMP versions).

- Gonzalo Tornaria and William Stein (2006-03-02): greatly improved
  python/GMP conversion; hashing

- William Stein and Naqi Jaffery (2006-03-06): height, sqrt examples,
  and improve behavior of sqrt.

- David Harvey (2006-09-15): added nth_root

- Pablo De Napoli (2007-04-01): corrected the implementations of
  multiplicative_order, is_one; optimized __bool__ ; documented:
  lcm,gcd

- John Cremona (2009-05-15): added support for local and global
  logarithmic heights.

- Travis Scrimshaw (2012-10-18): Added doctests for full coverage.

- Vincent Delecroix (2013): continued fraction

- Vincent Delecroix (2017-05-03): faster integer-rational comparison

- Vincent Klein (2017-05-11): add __mpq__() to class Rational

- Vincent Klein (2017-05-22): Rational constructor support gmpy2.mpq
  or gmpy2.mpz parameter. Add __mpz__ to class Rational.

TESTS::

    sage: a = -2/3
    sage: a == loads(dumps(a))
    True
"""
from __future__ import annotations

from cpython import *

import sage.rings.fast_arith
from sage.categories.map import Map
from sage.categories.morphism import Morphism
from sage.libs.gmp.all import *
from sage.rings.integer import Integer
from sage.structure.element import Element


class Rational:
    ...

class Rational:
    """
    A rational number.

    Rational numbers are implemented using the GMP C library.

    EXAMPLES::

        sage: a = -2/3
        sage: type(a)
        <class 'sage.rings.rational.Rational'>
        sage: parent(a)
        Rational Field
        sage: Rational('1/0')
        Traceback (most recent call last):
        ...
        TypeError: unable to convert '1/0' to a rational
        sage: Rational(1.5)
        3/2
        sage: Rational('9/6')
        3/2
        sage: Rational((2^99,2^100))
        1/2
        sage: Rational(("2", "10"), 16)
        1/8
        sage: Rational(QQbar(125/8).nth_root(3))                                        # needs sage.rings.number_field
        5/2
        sage: Rational(AA(209735/343 - 17910/49*golden_ratio).nth_root(3)               # needs sage.rings.number_field sage.symbolic
        ....:          + 3*AA(golden_ratio))
        53/7
        sage: QQ(float(1.5))
        3/2
        sage: QQ(RDF(1.2))
        6/5

    Conversion from fractions::

        sage: import fractions
        sage: f = fractions.Fraction(1r, 2r)
        sage: Rational(f)
        1/2

    Conversion from PARI::

        sage: Rational(pari('-939082/3992923'))                                         # needs sage.libs.pari
        -939082/3992923
        sage: Rational(pari('Pol([-1/2])'))  #9595                                      # needs sage.libs.pari
        -1/2

    Conversions from numpy::

        sage: # needs numpy
        sage: import numpy as np
        sage: QQ(np.int8('-15'))
        -15
        sage: QQ(np.int16('-32'))
        -32
        sage: QQ(np.int32('-19'))
        -19
        sage: QQ(np.uint32('1412'))
        1412

        sage: QQ(np.float16('12'))                                                      # needs numpy
        12

    Conversions from gmpy2::

        sage: from gmpy2 import *
        sage: QQ(mpq('3/4'))
        3/4
        sage: QQ(mpz(42))
        42
        sage: Rational(mpq(2/3))
        2/3
        sage: Rational(mpz(5))
        5

    TESTS:

    Check that :issue:`28321` is fixed::

        sage: QQ((2r^100r, 3r^100r))
        1267650600228229401496703205376/515377520732011331036461129765621272702107522001
        sage: QQ((-2r^100r, -3r^100r))
        1267650600228229401496703205376/515377520732011331036461129765621272702107522001
    """
    ord = valuation
    numer = numerator
    denom = denominator
    __round__ = round
    is_integer = is_integral

    def _richcmp_(left, right, op: int):
        """
        Compare two rational numbers.

        INPUT:

        - ``left``, ``right`` -- objects

        - ``op`` -- integer

        EXAMPLES::

            sage: 1/3 < 2/3
            True
            sage: 2/3 < 1/3
            False
            sage: 4/5 < 2.0
            True
            sage: 4/5 < 0.8
            False

            sage: ones = [1, 1r, 1l, 1/1, 1.0r, 1.0]
            sage: twos = [2, 2r, 2l, 2/1, 2.0r, 2.0]
            sage: threes = [3, 3r, 3l, 3/1, 3.0r, 3.0]
            sage: from itertools import product
            sage: for one,two,three in product(ones,twos,threes):
            ....:     assert one < two < three
            ....:     assert one <= two <= three
            ....:     assert three > two > one
            ....:     assert three >= two >= one
            ....:     assert one != two and one != three and two != three
            sage: for one1, one2 in product(ones,repeat=2):
            ....:     assert (one1 == one2) is True
            ....:     assert (one1 <= one2) is True
            ....:     assert (one1 >= one2) is True

        Comparisons with gmpy2 values (:issue:`28394`)::

            sage: import gmpy2
            sage: values = [(-2,5),(-1,3),(0,1),(2,9),(1,1),(73,2)]
            sage: for num1, den1 in values:
            ....:     for num2, den2 in values:
            ....:         a1 = QQ((num1, den1))
            ....:         a2 = QQ((num2, den2))
            ....:         b1 = gmpy2.mpq(num1, den1)
            ....:         b2 = gmpy2.mpq(num2, den2)
            ....:         assert a1 == b1 and b1 == a1 and a2 == b2 and b2 == a2
            ....:         assert (a1 == a2) == (b1 == b2) == (a1 == b2) == (b1 == a2)
            ....:         assert (a1 != a2) == (b1 != b2) == (a1 != b2) == (b1 != a2)
            ....:         assert (a1 <  a2) == (b1 <  b2) == (a1 <  b2) == (b1 <  a2)
            ....:         assert (a1 <= a2) == (b1 <= b2) == (a1 <= b2) == (b1 <= a2)
            ....:         assert (a1 >  a2) == (b1 >  b2) == (a1 >  b2) == (b1 >  a2)
            ....:         assert (a1 >= a2) == (b1 >= b2) == (a1 >= b2) == (b1 >= a2)
        """

    def _add_(self, right):
        """
        Return ``right`` plus ``self``.

        EXAMPLES::

            sage: (2/3)._add_(1/6)
            5/6
            sage: (1/3)._add_(1/2)
            5/6
        """

    def _sub_(self, right):
        """
        Return ``self`` minus ``right``.

        EXAMPLES::

            sage: (2/3)._sub_(1/6)
            1/2
        """

    def _neg_(self):
        """
        Negate ``self``.

        EXAMPLES::

            sage: -(2/3) # indirect doctest
            -2/3
        """

    def _mul_(self, right):
        """
        Return ``self`` times ``right``.

        EXAMPLES::

            sage: (3/14)._mul_(2/3)
            1/7
        """

    def _div_(self, right):
        """
        Return ``self`` divided by ``right``.

        EXAMPLES::

            sage: 2/3 # indirect doctest
            2/3
            sage: 3/0 # indirect doctest
            Traceback (most recent call last):
            ...
            ZeroDivisionError: rational division by zero
        """

    def _pow_(self, other):
        """
        Raise ``self`` to the rational power ``other``.

        EXAMPLES::

            sage: (2/3)^5
            32/243
            sage: (-1/1)^(1/3)                                                          # needs sage.symbolic
            (-1)^(1/3)
            sage: (2/3)^(3/4)                                                           # needs sage.symbolic
            (2/3)^(3/4)
            sage: (-1/3)^0
            1
            sage: a = (0/1)^(0/1); a
            1
            sage: type(a)
            <class 'sage.rings.rational.Rational'>

        If the result is rational, it is returned as a rational::

            sage: a = (4/9)^(1/2); a
            2/3
            sage: parent(a)
            Rational Field
            sage: (-27/125)^(1/3)                                                       # needs sage.symbolic
            3/5*(-1)^(1/3)
            sage: (-27/125)^(1/2)                                                       # needs sage.symbolic
            3/5*sqrt(-3/5)

        The result is normalized to have the rational power in the numerator::

            sage: 2^(-1/2)                                                              # needs sage.symbolic
            1/2*sqrt(2)
            sage: 8^(-1/5)                                                              # needs sage.symbolic
            1/8*8^(4/5)
            sage: 3^(-3/2)                                                              # needs sage.symbolic
            1/9*sqrt(3)

        TESTS::

            sage: QQ(0)^(-1)
            Traceback (most recent call last):
            ...
            ZeroDivisionError: rational division by zero

        This works even if the base is a Python integer::

            sage: int(2)^(1/2)                                                          # needs sage.symbolic
            sqrt(2)
            sage: a = int(2)^(3/1); a
            8
            sage: type(a)
            <class 'sage.rings.rational.Rational'>

        The exponent must fit in a ``long`` unless the base is -1, 0, or 1::

            sage: (1/2)^(2^100)
            Traceback (most recent call last):
            ...
            OverflowError: exponent must be at most 2147483647           # 32-bit
            OverflowError: exponent must be at most 9223372036854775807  # 64-bit
            sage: (1/2)^(-2^100)
            Traceback (most recent call last):
            ...
            OverflowError: exponent must be at most 2147483647           # 32-bit
            OverflowError: exponent must be at most 9223372036854775807  # 64-bit
            sage: QQ(-1)^(2^100)                                                        # needs sage.symbolic
            1
        """

    def __cinit__(self):
        """
        Initialize ``self`` as an element of `\\QQ`.

        EXAMPLES::

            sage: p = Rational(3) # indirect doctest
            sage: p.parent()
            Rational Field
        """

    def __init__(self, x=None, base: int=0):
        """
        Create a new rational number.

        INPUT:

        - ``x`` -- object (default: ``None``)

        - ``base`` -- base if ``x`` is a string

        EXAMPLES::

            sage: a = Rational()
            sage: a.__init__(7); a
            7
            sage: a.__init__('70', base=8); a
            56
            sage: a.__init__(pari('2/3')); a                                            # needs sage.libs.pari
            2/3
            sage: a.__init__('-h/3ki', 32); a
            -17/3730
            sage: from gmpy2 import mpq
            sage: a.__init__(mpq('3/5')); a
            3/5

        TESTS:

        Check that :issue:`19835` is fixed::

            sage: QQ((0r,-1r))
            0
            sage: QQ((-1r,-1r))
            1

        .. NOTE::

           This is for doctesting purposes only.  Rationals are defined
           to be immutable.
        """

    def __reduce__(self):
        """
        Used in pickling rational numbers.

        EXAMPLES::

            sage: a = 3/5
            sage: a.__reduce__()
            (<cyfunction make_rational at ...>, ('3/5',))
        """

    def __index__(self):
        """
        Needed so integers can be used as list indices.

        EXAMPLES::

            sage: v = [1,2,3,4,5]
            sage: v[3/1]
            4
            sage: v[3/2]
            Traceback (most recent call last):
            ...
            TypeError: unable to convert rational 3/2 to an integer
        """

    def list(self):
        """
        Return a list with the rational element in it, to be compatible
        with the method for number fields.

        OUTPUT: the list ``[self]``

        EXAMPLES::

            sage: m = 5/3
            sage: m.list()
            [5/3]
        """

    def continued_fraction_list(self, type='std'):
        """
        Return the list of partial quotients of this rational number.

        INPUT:

        - ``type`` -- either ``'std'`` (the default) for the standard continued
          fractions or ``'hj'`` for the Hirzebruch-Jung ones

        EXAMPLES::

            sage: (13/9).continued_fraction_list()
            [1, 2, 4]
            sage: 1 + 1/(2 + 1/4)
            13/9

            sage: (225/157).continued_fraction_list()
            [1, 2, 3, 4,  5]
            sage: 1 + 1/(2 + 1/(3 + 1/(4 + 1/5)))
            225/157

            sage: (fibonacci(20)/fibonacci(19)).continued_fraction_list()               # needs sage.libs.pari
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2]

            sage: (-1/3).continued_fraction_list()
            [-1, 1, 2]

        Check that the partial quotients of an integer ``n`` is simply ``[n]``::

            sage: QQ(1).continued_fraction_list()
            [1]
            sage: QQ(0).continued_fraction_list()
            [0]
            sage: QQ(-1).continued_fraction_list()
            [-1]

        Hirzebruch-Jung continued fractions::

            sage: (11/19).continued_fraction_list("hj")
            [1, 3, 2, 3, 2]
            sage: 1 - 1/(3 - 1/(2 - 1/(3 - 1/2)))
            11/19

            sage: (225/137).continued_fraction_list("hj")
            [2, 3, 5, 10]
            sage: 2 - 1/(3 - 1/(5 - 1/10))
            225/137

            sage: (-23/19).continued_fraction_list("hj")
            [-1, 5, 4]
            sage: -1 - 1/(5 - 1/4)
            -23/19
        """

    def continued_fraction(self):
        """
        Return the continued fraction of that rational.

        EXAMPLES::

            sage: (641/472).continued_fraction()
            [1; 2, 1, 3, 1, 4, 1, 5]

            sage: a = (355/113).continued_fraction(); a
            [3; 7, 16]
            sage: a.n(digits=10)                                                        # needs sage.rings.real_mpfr
            3.141592920
            sage: pi.n(digits=10)                                                       # needs sage.rings.real_mpfr sage.symbolic
            3.141592654

        It's almost pi!
        """

    def __copy__(self):
        """
        EXAMPLES::

            sage: a = -17/37
            sage: copy(a) is a
            True

        Coercion does not make a new copy::

            sage: QQ(a) is a
            True

        Calling the constructor directly makes a new copy::

            sage: Rational(a) is a
            False
        """

    def __deepcopy__(self, memo):
        """
        EXAMPLES::

            sage: a = -17/37
            sage: deepcopy(a) is a
            True
        """

    def __dealloc__(self):
        """
        Free memory occupied by this rational number.

        EXAMPLES::

            sage: a = -17/37
            sage: del a          # indirect test
        """

    def __repr__(self):
        """
        Return string representation of this rational number.

        EXAMPLES::

            sage: a = -17/37; a.__repr__()
            '-17/37'
        """

    def _latex_(self):
        """
        Return Latex representation of this rational number.

        EXAMPLES::

            sage: a = -17/37
            sage: a._latex_()
            '-\x0crac{17}{37}'
        """

    def _symbolic_(self, sring):
        """
        Return this rational as symbolic expression.

        EXAMPLES::

            sage: ex = SR(QQ(7)/3); ex                                                  # needs sage.symbolic
            7/3
            sage: parent(ex)                                                            # needs sage.symbolic
            Symbolic Ring
        """

    def _sympy_(self):
        """
        Convert Sage ``Rational`` to SymPy ``Rational``.

        EXAMPLES::

            sage: # needs sympy
            sage: n = 1/2; n._sympy_()
            1/2
            sage: n = -1/5; n._sympy_()
            -1/5
            sage: from sympy import Symbol
            sage: QQ(1) + Symbol('x')*QQ(2)
            2*x + 1
        """

    def __mpz__(self):
        """
        Return a gmpy2 ``mpz`` if this Rational is an integer.

        EXAMPLES::

            sage: q = 6/2
            sage: q.__mpz__()
            mpz(3)
            sage: q = 1/4
            sage: q.__mpz__()
            Traceback (most recent call last):
            ...
            TypeError: unable to convert rational 1/4 to an integer

        TESTS::

            sage: QQ().__mpz__(); raise NotImplementedError("gmpy2 is not installed")
            Traceback (most recent call last):
            ...
            NotImplementedError: gmpy2 is not installed
        """

    def __mpq__(self):
        """
        Convert Sage ``Rational`` to gmpy2 ``Rational``.

        EXAMPLES::

            sage: r = 5/3
            sage: r.__mpq__()
            mpq(5,3)
            sage: from gmpy2 import mpq
            sage: mpq(r)
            mpq(5,3)
        """

    def _magma_init_(self, magma):
        """
        Return the magma representation of ``self``.

        EXAMPLES::

            sage: n = -485/82847
            sage: n._magma_init_(magma)                         # optional - magma
            '-485/82847'
        """

    def _regina_(self, regina):
        """
        Return a Regina Rational.

        EXAMPLES::

            sage: r53 = regina(5/3); (r53, type(r53), type(r53._inst))  # optional regina
            (5/3,
            <class 'sage.interfaces.regina.ReginaElement'>,
            <class 'regina.engine.Rational'>)
        """

    @property
    def __array_interface__(self):
        """
        Used for NumPy conversion. If ``self`` is integral, it converts to
        an ``Integer``. Otherwise it converts to a double floating point
        value.

        EXAMPLES::

            sage: # needs numpy
            sage: import numpy
            sage: numpy.array([1, 2, 3/1])
            array([1, 2, 3])
            sage: numpy.array(QQ(2**40)).dtype
            dtype('int64')
            sage: numpy.array(QQ(2**400)).dtype
            dtype('O')
            sage: numpy.array([1, 1/2, 3/4])
            array([1.  , 0.5 , 0.75])
        """

    def _mathml_(self):
        """
        Return mathml representation of this rational number.

        EXAMPLES::

            sage: a = -17/37; a._mathml_()
            '<mo>-</mo><mfrac><mrow><mn>17</mn></mrow><mrow><mn>37</mn></mrow></mfrac>'
        """

    def _im_gens_(self, codomain, im_gens, base_map=None):
        """
        Return the image of ``self`` under the homomorphism from the rational
        field to ``codomain``.

        This always just returns ``self`` coerced into the ``codomain``.

        INPUT:

        - ``codomain`` -- object (usually a ring)

        - ``im_gens`` -- list of elements of ``codomain``

        EXAMPLES::

            sage: a = -17/37
            sage: a._im_gens_(QQ, [1/1])
            -17/37
        """

    def content(self, other):
        """
        Return the content of ``self`` and ``other``, i.e., the unique positive
        rational number `c` such that ``self/c`` and ``other/c`` are coprime
        integers.

        ``other`` can be a rational number or a list of rational numbers.

        EXAMPLES::

            sage: a = 2/3
            sage: a.content(2/3)
            2/3
            sage: a.content(1/5)
            1/15
            sage: a.content([2/5, 4/9])
            2/45
        """

    def valuation(self, p):
        """
        Return the power of ``p`` in the factorization of ``self``.

        INPUT:

        - ``p`` -- a prime number

        OUTPUT:

        (integer or infinity) ``Infinity`` if ``self`` is zero, otherwise the
        (positive or negative) integer `e` such that ``self`` = `m*p^e`
        with `m` coprime to `p`.

        .. NOTE::

           See also :meth:`val_unit()` which returns the pair `(e,m)`. The
           function :meth:`ord()` is an alias for :meth:`valuation()`.

        EXAMPLES::

            sage: x = -5/9
            sage: x.valuation(5)
            1
            sage: x.ord(5)
            1
            sage: x.valuation(3)
            -2
            sage: x.valuation(2)
            0

        Some edge cases::

            sage: (0/1).valuation(4)
            +Infinity
            sage: (7/16).valuation(4)
            -2
        """

    def local_height(self, p, prec=None):
        """
        Return the local height of this rational number at the prime `p`.

        INPUT:

        - ``p`` -- a prime number

        - ``prec`` -- integer (default: default :class:`RealField` precision);
          desired floating point precision

        OUTPUT:

        (real) The local height of this rational number at the
        prime `p`.

        EXAMPLES::

            sage: a = QQ(25/6)
            sage: a.local_height(2)                                                     # needs sage.rings.real_mpfr
            0.693147180559945
            sage: a.local_height(3)                                                     # needs sage.rings.real_mpfr
            1.09861228866811
            sage: a.local_height(5)                                                     # needs sage.rings.real_mpfr
            0.000000000000000
        """

    def local_height_arch(self, prec=None):
        """
        Return the Archimedean local height of this rational number at the
        infinite place.

        INPUT:

        - ``prec`` -- integer (default: default :class:`RealField` precision);
          desired floating point precision

        OUTPUT:

        (real) The local height of this rational number `x` at the
        unique infinite place of `\\QQ`, which is
        `\\max(\\log(|x|),0)`.

        EXAMPLES::

            sage: a = QQ(6/25)
            sage: a.local_height_arch()                                                 # needs sage.rings.real_mpfr
            0.000000000000000
            sage: (1/a).local_height_arch()                                             # needs sage.rings.real_mpfr
            1.42711635564015
            sage: (1/a).local_height_arch(100)                                          # needs sage.rings.real_mpfr
            1.4271163556401457483890413081
        """

    def global_height_non_arch(self, prec=None):
        """
        Return the total non-archimedean component of the height of this
        rational number.

        INPUT:

        - ``prec`` -- integer (default: default :class:`RealField` precision);
          desired floating point precision

        OUTPUT:

        (real) The total non-archimedean component of the height of
        this rational number.

        ALGORITHM:

        This is the sum of the local heights at all primes `p`, which
        may be computed without factorization as the log of the
        denominator.

        EXAMPLES::

            sage: a = QQ(5/6)
            sage: a.support()
            [2, 3, 5]
            sage: a.global_height_non_arch()                                            # needs sage.rings.real_mpfr
            1.79175946922805
            sage: [a.local_height(p) for p in a.support()]                              # needs sage.rings.real_mpfr
            [0.693147180559945, 1.09861228866811, 0.000000000000000]
            sage: sum([a.local_height(p) for p in a.support()])                         # needs sage.rings.real_mpfr
            1.79175946922805
        """

    def global_height_arch(self, prec=None):
        """
        Return the total archimedean component of the height of this rational
        number.

        INPUT:

        - ``prec`` -- integer (default: default :class:`RealField` precision);
          desired floating point precision

        OUTPUT:

        (real) The total archimedean component of the height of
        this rational number.

        ALGORITHM:

        Since `\\QQ` has only one infinite place this is just the value
        of the local height at that place.  This separate function is
        included for compatibility with number fields.

        EXAMPLES::

            sage: a = QQ(6/25)
            sage: a.global_height_arch()                                                # needs sage.rings.real_mpfr
            0.000000000000000
            sage: (1/a).global_height_arch()                                            # needs sage.rings.real_mpfr
            1.42711635564015
            sage: (1/a).global_height_arch(100)                                         # needs sage.rings.real_mpfr
            1.4271163556401457483890413081
        """

    def global_height(self, prec=None):
        """
        Return the absolute logarithmic height of this rational number.

        INPUT:

        - ``prec`` -- integer (default: default :class:`RealField` precision);
          desired floating point precision

        OUTPUT:

        (real) The absolute logarithmic height of this rational number.

        ALGORITHM:

        The height is the sum of the total archimedean and
        non-archimedean components, which is equal to
        `\\max(\\log(n),\\log(d))` where `n,d` are the numerator and
        denominator of the rational number.

        EXAMPLES::

            sage: # needs sage.rings.real_mpfr
            sage: a = QQ(6/25)
            sage: a.global_height_arch() + a.global_height_non_arch()
            3.21887582486820
            sage: a.global_height()
            3.21887582486820
            sage: (1/a).global_height()
            3.21887582486820
            sage: QQ(0).global_height()
            0.000000000000000
            sage: QQ(1).global_height()
            0.000000000000000
        """

    def is_square(self):
        """
        Return whether or not this rational number is a square.

        OUTPUT: boolean

        EXAMPLES::

            sage: x = 9/4
            sage: x.is_square()
            True
            sage: x = (7/53)^100
            sage: x.is_square()
            True
            sage: x = 4/3
            sage: x.is_square()
            False
            sage: x = -1/4
            sage: x.is_square()
            False
        """

    def is_norm(self, L, element=False, proof=True):
        """
        Determine whether ``self`` is the norm of an element of ``L``.

        INPUT:

        - ``L`` -- a number field
        - ``element`` -- boolean (default: ``False``); whether to also output
          an element of which ``self`` is a norm
        - ``proof`` -- if ``True``, then the output is correct unconditionally;
          if ``False``, then the output assumes GRH

        OUTPUT:

        If element is ``False``, then the output is a boolean ``B``, which is
        ``True`` if and only if ``self`` is the norm of an element of ``L``.
        If ``element`` is ``False``, then the output is a pair ``(B, x)``,
        where ``B`` is as above. If ``B`` is ``True``, then ``x`` an element of
        ``L`` such that ``self == x.norm()``. Otherwise, ``x is None``.

        ALGORITHM:

        Uses the PARI function :pari:`bnfisnorm`. See :meth:`_bnfisnorm()`.

        EXAMPLES::

            sage: # needs sage.rings.number_field
            sage: x = polygen(QQ, 'x')
            sage: K = NumberField(x^2 - 2, 'beta')
            sage: (1/7).is_norm(K)
            True
            sage: (1/10).is_norm(K)
            False
            sage: 0.is_norm(K)
            True
            sage: (1/7).is_norm(K, element=True)
            (True, 1/7*beta + 3/7)
            sage: (1/10).is_norm(K, element=True)
            (False, None)
            sage: (1/691).is_norm(QQ, element=True)
            (True, 1/691)

        The number field doesn't have to be defined by an
        integral polynomial::

            sage: B, e = (1/5).is_norm(QuadraticField(5/4, 'a'), element=True)          # needs sage.rings.number_field
            sage: B                                                                     # needs sage.rings.number_field
            True
            sage: e.norm()                                                              # needs sage.rings.number_field
            1/5

        A non-Galois number field::

            sage: # needs sage.rings.number_field
            sage: K.<a> = NumberField(x^3 - 2)
            sage: B, e = (3/5).is_norm(K, element=True); B
            True
            sage: e.norm()
            3/5
            sage: 7.is_norm(K)                                                          # needs sage.groups
            Traceback (most recent call last):
            ...
            NotImplementedError: is_norm is not implemented unconditionally
             for norms from non-Galois number fields
            sage: 7.is_norm(K, proof=False)
            False

        AUTHORS:

        - Craig Citro (2008-04-05)

        - Marco Streng (2010-12-03)
        """

    def is_perfect_power(self, expected_value=False):
        """
        Return ``True`` if ``self`` is a perfect power.

        INPUT:

        - ``expected_value`` -- boolean; whether or not this rational is
          expected to be a perfect power. This does not affect the correctness
          of the output, only the runtime.

        If ``expected_value`` is ``False`` (default) it will check the
        smallest of the numerator and denominator is a perfect power
        as a first step, which is often faster than checking if the
        quotient is a perfect power.

        EXAMPLES::

            sage: (4/9).is_perfect_power()
            True
            sage: (144/1).is_perfect_power()
            True
            sage: (4/3).is_perfect_power()
            False
            sage: (2/27).is_perfect_power()
            False
            sage: (4/27).is_perfect_power()
            False
            sage: (-1/25).is_perfect_power()
            False
            sage: (-1/27).is_perfect_power()
            True
            sage: (0/1).is_perfect_power()
            True

        The second parameter does not change the result, but may
        change the runtime.

        ::

            sage: (-1/27).is_perfect_power(True)
            True
            sage: (-1/25).is_perfect_power(True)
            False
            sage: (2/27).is_perfect_power(True)
            False
            sage: (144/1).is_perfect_power(True)
            True

        This test makes sure we workaround a bug in GMP (see :issue:`4612`)::

            sage: [-a for a in srange(100) if not QQ(-a^3).is_perfect_power()]
            []
            sage: [-a for a in srange(100) if not QQ(-a^3).is_perfect_power(True)]
            []
        """

    def squarefree_part(self):
        """
        Return the square free part of `x`, i.e., an integer `z` such
        that `x = z y^2`, for a perfect square `y^2`.

        EXAMPLES::

            sage: a = 1/2
            sage: a.squarefree_part()
            2
            sage: b = a/a.squarefree_part()
            sage: b, b.is_square()
            (1/4, True)
            sage: a = 24/5
            sage: a.squarefree_part()
            30
        """

    def is_padic_square(self, p, check=True):
        """
        Determines whether this rational number is a square in `\\QQ_p` (or in
        `R` when ``p = infinity``).

        INPUT:

        - ``p`` -- a prime number, or ``infinity``

        - ``check`` -- boolean (default: ``True``); check if `p` is prime

        EXAMPLES::

            sage: QQ(2).is_padic_square(7)
            True
            sage: QQ(98).is_padic_square(7)
            True
            sage: QQ(2).is_padic_square(5)
            False

        TESTS::

            sage: QQ(5/7).is_padic_square(int(2))
            False
        """

    def val_unit(self, p):
        """
        Return a pair: the `p`-adic valuation of ``self``, and the `p`-adic
        unit of ``self``, as a :class:`Rational`.

        We do not require the `p` be prime, but it must be at least 2. For
        more documentation see :meth:`Integer.val_unit()`.

        INPUT:

        - ``p`` -- a prime

        OUTPUT:

        - integer; the `p`-adic valuation of this rational

        - ``Rational``; `p`-adic unit part of ``self``

        EXAMPLES::

            sage: (-4/17).val_unit(2)
            (2, -1/17)
            sage: (-4/17).val_unit(17)
            (-1, -4)
            sage: (0/1).val_unit(17)
            (+Infinity, 1)

        AUTHORS:

        - David Roe (2007-04-12)
        """

    def prime_to_S_part(self, S=...):
        """
        Return ``self`` with all powers of all primes in ``S`` removed.

        INPUT:

        - ``S`` -- list or tuple of primes

        OUTPUT: rational

        .. NOTE::

           Primality of the entries in `S` is not checked.

        EXAMPLES::

            sage: QQ(3/4).prime_to_S_part()
            3/4
            sage: QQ(3/4).prime_to_S_part([2])
            3
            sage: QQ(-3/4).prime_to_S_part([3])
            -1/4
            sage: QQ(700/99).prime_to_S_part([2,3,5])
            7/11
            sage: QQ(-700/99).prime_to_S_part([2,3,5])
            -7/11
            sage: QQ(0).prime_to_S_part([2,3,5])
            0
            sage: QQ(-700/99).prime_to_S_part([])
            -700/99
        """

    def sqrt(self, prec=None, extend=True, all=False):
        """
        The square root function.

        INPUT:

        - ``prec`` -- integer (default: ``None``); if ``None``, returns
          an exact square root; otherwise returns a numerical square root if
          necessary, to the given bits of precision.

        - ``extend`` -- boolean (default: ``True``); if ``True``, return a
          square root in an extension ring, if necessary. Otherwise, raise a
          :exc:`ValueError` if the square is not in the base ring. Ignored if
          ``prec`` is not ``None``.

        - ``all`` -- boolean (default: ``False``); if ``True``, return all
          square roots of ``self`` (a list of length 0, 1, or 2)

        EXAMPLES::

            sage: x = 25/9
            sage: x.sqrt()
            5/3
            sage: sqrt(x)
            5/3
            sage: x = 64/4
            sage: x.sqrt()
            4
            sage: x = 100/1
            sage: x.sqrt()
            10
            sage: x.sqrt(all=True)
            [10, -10]
            sage: x = 81/5
            sage: x.sqrt()                                                              # needs sage.symbolic
            9*sqrt(1/5)
            sage: x = -81/3
            sage: x.sqrt()                                                              # needs sage.symbolic
            3*sqrt(-3)

        ::

            sage: n = 2/3
            sage: n.sqrt()                                                              # needs sage.symbolic
            sqrt(2/3)

            sage: # needs sage.rings.real_mpfr
            sage: n.sqrt(prec=10)
            0.82
            sage: n.sqrt(prec=100)
            0.81649658092772603273242802490
            sage: n.sqrt(prec=100)^2
            0.66666666666666666666666666667
            sage: n.sqrt(prec=53, all=True)
            [0.816496580927726, -0.816496580927726]
            sage: sqrt(-2/3, prec=53)
            0.816496580927726*I
            sage: sqrt(-2/3, prec=53, all=True)
            [0.816496580927726*I, -0.816496580927726*I]

            sage: n.sqrt(extend=False)
            Traceback (most recent call last):
            ...
            ValueError: square root of 2/3 not a rational number
            sage: n.sqrt(extend=False, all=True)
            []
            sage: sqrt(-2/3, all=True)                                                  # needs sage.symbolic
            [sqrt(-2/3), -sqrt(-2/3)]

        TESTS:

        Ensure that :issue:`37153` is fixed, so that behaviour aligns
        with other rings and fields.
        See :issue:`9466` and :issue:`26509` for context::

            sage: QQ(3).sqrt(extend=False, all=True)
            []
            sage: QQ(-1).sqrt(extend=False, all=True)
            []

        AUTHORS:

        - Naqi Jaffery (2006-03-05): some examples
        """

    def period(self):
        """
        Return the period of the repeating part of the decimal expansion of
        this rational number.

        ALGORITHM:

        When a rational number `n/d` with `(n,d)=1` is
        expanded, the period begins after `s` terms and has length
        `t`, where `s` and `t` are the smallest numbers satisfying
        `10^s=10^{s+t} \\mod d`. In general if `d=2^a 5^b m` where `m`
        is coprime to 10, then `s=\\max(a,b)` and `t` is the order of
        10 modulo `m`.

        EXAMPLES::

            sage: (1/7).period()                                                        # needs sage.libs.pari
            6
            sage: RR(1/7)                                                               # needs sage.rings.real_mpfr
            0.142857142857143
            sage: (1/8).period()                                                        # needs sage.libs.pari
            1
            sage: RR(1/8)                                                               # needs sage.rings.real_mpfr
            0.125000000000000
            sage: RR(1/6)                                                               # needs sage.rings.real_mpfr
            0.166666666666667
            sage: (1/6).period()                                                        # needs sage.libs.pari
            1
            sage: x = 333/106
            sage: x.period()                                                            # needs sage.libs.pari
            13
            sage: RealField(200)(x)                                                     # needs sage.rings.real_mpfr
            3.1415094339622641509433962264150943396226415094339622641509
        """

    def nth_root(self, n: int):
        """
        Compute the `n`-th root of ``self``, or raises a
        :exc:`ValueError` if ``self`` is not a perfect `n`-th power.

        INPUT:

        - ``n`` -- integer (must fit in C ``int`` type)

        AUTHORS:

        - David Harvey (2006-09-15)

        EXAMPLES::

            sage: (25/4).nth_root(2)
            5/2
            sage: (125/8).nth_root(3)
            5/2
            sage: (-125/8).nth_root(3)
            -5/2
            sage: (25/4).nth_root(-2)
            2/5

        ::

            sage: (9/2).nth_root(2)
            Traceback (most recent call last):
            ...
            ValueError: not a perfect 2nd power

        ::

            sage: (-25/4).nth_root(2)
            Traceback (most recent call last):
            ...
            ValueError: cannot take even root of negative number
        """

    def is_nth_power(self, n: int):
        """
        Return ``True`` if ``self`` is an `n`-th power, else ``False``.

        INPUT:

        - ``n`` -- integer (must fit in C ``int`` type)

        .. NOTE::

           Use this function when you need to test if a rational
           number is an `n`-th power, but do not need to know the value
           of its `n`-th root.  If the value is needed, use :meth:`nth_root()`.

        AUTHORS:

        - John Cremona (2009-04-04)

        EXAMPLES::

            sage: QQ(25/4).is_nth_power(2)
            True
            sage: QQ(125/8).is_nth_power(3)
            True
            sage: QQ(-125/8).is_nth_power(3)
            True
            sage: QQ(25/4).is_nth_power(-2)
            True

            sage: QQ(9/2).is_nth_power(2)
            False
            sage: QQ(-25).is_nth_power(2)
            False
        """

    def str(self, base: int=10):
        """
        Return a string representation of ``self`` in the given ``base``.

        INPUT:

        - ``base`` -- integer (default: 10); base must be between 2 and 36

        OUTPUT: string

        EXAMPLES::

            sage: (-4/17).str()
            '-4/17'
            sage: (-4/17).str(2)
            '-100/10001'

        Note that the base must be at most 36.

        ::

            sage: (-4/17).str(40)
            Traceback (most recent call last):
            ...
            ValueError: base (=40) must be between 2 and 36
            sage: (-4/17).str(1)
            Traceback (most recent call last):
            ...
            ValueError: base (=1) must be between 2 and 36
        """

    def __float__(self):
        """
        Return floating point approximation to ``self`` as a Python float.

        OUTPUT: float

        EXAMPLES::

            sage: (-4/17).__float__()
            -0.23529411764705882
            sage: float(-4/17)
            -0.23529411764705882
            sage: float(1/3)
            0.3333333333333333
            sage: float(1/10)
            0.1
            sage: n = QQ(902834098234908209348209834092834098); float(n)
            9.028340982349083e+35

        TESTS:

        Test that conversion agrees with `RR`::

            sage: Q = [a/b for a in [-99..99] for b in [1..99]]
            sage: all(RDF(q) == RR(q) for q in Q)
            True

        Test that the conversion has correct rounding on simple rationals::

            sage: for p in [-100..100]:                                                 # needs sage.rings.real_mpfr
            ....:   for q in [1..100]:
            ....:       r = RDF(p/q)
            ....:       assert (RR(r).exact_rational() - p/q) <= r.ulp()/2

        Test larger rationals::

            sage: Q = continued_fraction(pi).convergents()[:100]                        # needs sage.symbolic
            sage: all(RDF(q) == RR(q) for q in Q)
            True

        At some point, the continued fraction and direct conversion
        to ``RDF`` should agree::

            sage: RDFpi = RDF(pi)                                                       # needs sage.symbolic
            sage: all(RDF(q) == RDFpi for q in Q[20:])                                  # needs sage.symbolic
            True
        """

    def __hash__(self):
        """
        Return hash of ``self``.

        OUTPUT: integer

        EXAMPLES::

            sage: QQ(42).__hash__()
            42
            sage: QQ(1/42).__hash__()
            1488680910            # 32-bit
            -7658195599476688946  # 64-bit
            sage: n = ZZ.random_element(10^100)
            sage: hash(n) == hash(QQ(n)) or n
            True
            sage: hash(-n) == hash(-QQ(n)) or n
            True
            sage: hash(-4/17)
            -47583156            # 32-bit
            8709371129873690700  # 64-bit
        """

    def __getitem__(self, n: int):
        """
        Return ``n``-th element of ``self``, viewed as a list. This is for
        consistency with how number field elements work.

        INPUT:

        - ``n`` -- integer (error if not 0 or -1)

        OUTPUT: rational

        EXAMPLES::

            sage: (-4/17)[0]
            -4/17
            sage: (-4/17)[1]
            Traceback (most recent call last):
            ...
            IndexError: index n (=1) out of range; it must be 0
            sage: (-4/17)[-1]   # indexing from the right
            -4/17
        """

    def __add__(left, right):
        """
        Return ``left`` plus ``right``.

        EXAMPLES::

            sage: (2/3) + (1/6)
            5/6
            sage: (1/3) + (1/2)
            5/6
            sage: (1/3) + 2
            7/3
        """

    def __sub__(left, right):
        """
        Return ``left`` minus ``right``.

        EXAMPLES::

            sage: 11/3 - 5/4
            29/12

            sage: (2/3) - 2
            -4/3
            sage: (-2/3) - 1
            -5/3
            sage: (2/3) - (-3)
            11/3
            sage: (-2/3) - (-3)
            7/3
            sage: 2/3 - polygen(QQ)
            -x + 2/3
        """

    def __mul__(left, right):
        """
        Return ``left`` times ``right``.

        EXAMPLES::

            sage: (3/14) * 2/3
            1/7
            sage: (3/14) * 10
            15/7
            sage: 3/14 * polygen(QQ)
            3/14*x
        """

    def __truediv__(left, right):
        """
        Return ``left`` divided by ``right``.

        EXAMPLES::

            sage: QQ((2,3)) / QQ((-5,4))
            -8/15
            sage: QQ((22,3)) / 4
            11/6
            sage: QQ((-2,3)) / (-4)
            1/6
            sage: QQ((2,3)) / QQ.zero()
            Traceback (most recent call last):
            ...
            ZeroDivisionError: rational division by zero
        """

    def __invert__(self):
        """
        Return the multiplicative inverse of ``self``.

        OUTPUT: rational

        EXAMPLES::

            sage: (-4/17).__invert__()
            -17/4
            sage: ~(-4/17)
            -17/4
        """

    def __pos__(self):
        """
        Return ``self``.

        OUTPUT: rational

        EXAMPLES::

            sage: (-4/17).__pos__()
            -4/17
            sage: +(-4/17)
            -4/17
        """

    def __neg__(self):
        """
        Return the negative of ``self``.

        OUTPUT: rational

        EXAMPLES::

            sage: (-4/17).__neg__()
            4/17
            sage: - (-4/17)
            4/17
        """

    def __bool__(self):
        """
        Return ``True`` if this rational number is nonzero.

        OUTPUT: boolean

        EXAMPLES::

            sage: bool(0/5)
            False
            sage: bool(-4/17)
            True
        """

    def __abs__(self):
        """
        Return the absolute value of this rational number.

        OUTPUT: rational

        EXAMPLES::

            sage: (-4/17).__abs__()
            4/17
            sage: abs(-4/17)
            4/17
        """

    def sign(self):
        """
        Return the sign of this rational number, which is -1, 0, or 1
        depending on whether this number is negative, zero, or positive
        respectively.

        OUTPUT: integer

        EXAMPLES::

            sage: (2/3).sign()
            1
            sage: (0/3).sign()
            0
            sage: (-1/6).sign()
            -1
        """

    def mod_ui(self: Rational, n: int):
        """
        Return the remainder upon division of ``self`` by the unsigned long
        integer ``n``.

        INPUT:

        - ``n`` -- an unsigned long integer

        OUTPUT: integer

        EXAMPLES::

            sage: (-4/17).mod_ui(3)
            1
            sage: (-4/17).mod_ui(17)
            Traceback (most recent call last):
            ...
            ArithmeticError: The inverse of 0 modulo 17 is not defined.
        """

    def __mod__(x, y):
        """
        Return the remainder of division of ``x`` by ``y``, where ``y`` is
        something that can be coerced to an integer.

        INPUT:

        - ``other`` -- object that coerces to an integer

        OUTPUT: integer

        EXAMPLES::

            sage: (-4/17).__mod__(3/1)
            1

        TESTS:

        Check that :issue:`14870` is fixed::

            sage: int(4) % QQ(3)
            1
        """

    def norm(self):
        """
        Return the norm from `\\QQ` to `\\QQ` of `x` (which is just `x`). This
        was added for compatibility with :class:`NumberField`.

        OUTPUT: ``Rational`` -- reference to ``self``

        EXAMPLES::

            sage: (1/3).norm()
             1/3

        AUTHORS:

        - Craig Citro
        """

    def relative_norm(self):
        """
        Return the norm from Q to Q of x (which is just x). This was added for
        compatibility with NumberFields.

        EXAMPLES::

            sage: (6/5).relative_norm()
            6/5

            sage: QQ(7/5).relative_norm()
            7/5
        """

    def absolute_norm(self):
        """
        Return the norm from Q to Q of x (which is just x). This was added for
        compatibility with NumberFields.

        EXAMPLES::

            sage: (6/5).absolute_norm()
            6/5

            sage: QQ(7/5).absolute_norm()
            7/5
        """

    def trace(self):
        """
        Return the trace from `\\QQ` to `\\QQ` of `x` (which is just `x`). This
        was added for compatibility with :class:`NumberFields`.

        OUTPUT: ``Rational`` -- reference to ``self``

        EXAMPLES::

            sage: (1/3).trace()
             1/3

        AUTHORS:

        - Craig Citro
        """

    def charpoly(self, var='x'):
        """
        Return the characteristic polynomial of this rational number. This
        will always be just ``var - self``; this is really here so that code
        written for number fields won't crash when applied to rational
        numbers.

        INPUT:

        - ``var`` -- string

        OUTPUT: polynomial

        EXAMPLES::

            sage: (1/3).charpoly('x')
             x - 1/3

        The default is ``var='x'``. (:issue:`20967`)::

            sage: a = QQ(2); a.charpoly('x')
            x - 2


        AUTHORS:

        - Craig Citro
        """

    def minpoly(self, var='x'):
        """
        Return the minimal polynomial of this rational number. This will
        always be just ``x - self``; this is really here so that code written
        for number fields won't crash when applied to rational numbers.

        INPUT:

        - ``var`` -- string

        OUTPUT: polynomial

        EXAMPLES::

            sage: (1/3).minpoly()
            x - 1/3
            sage: (1/3).minpoly('y')
            y - 1/3

        AUTHORS:

        - Craig Citro
        """

    def _integer_(self, Z=None):
        """
        Return ``self`` coerced to an integer. Of course this rational number
        must have a denominator of 1.

        OUTPUT: integer

        EXAMPLES::

            sage: (-4/17)._integer_()
            Traceback (most recent call last):
            ...
            TypeError: no conversion of this rational to integer
            sage: (-4/1)._integer_()
            -4
        """

    def numerator(self):
        """
        Return the numerator of this rational number.
        :meth:`numer` is an alias of :meth:`numerator`.

        EXAMPLES::

            sage: x = 5/11
            sage: x.numerator()
            5

            sage: x = 9/3
            sage: x.numerator()
            3

            sage: x = -5/11
            sage: x.numer()
            -5
        """

    def __int__(self):
        """
        Convert this rational to a Python ``int``.

        This truncates ``self`` if ``self`` has a denominator (which is
        consistent with Python's ``int(floats)``).

        EXAMPLES::

            sage: int(7/1)
            7
            sage: int(7/2)
            3
        """

    def denominator(self):
        """
        Return the denominator of this rational number.
        :meth:`denom` is an alias of :meth:`denominator`.

        EXAMPLES::

            sage: x = -5/11
            sage: x.denominator()
            11

            sage: x = 9/3
            sage: x.denominator()
            1

            sage: x = 5/13
            sage: x.denom()
            13
        """

    def as_integer_ratio(self):
        """
        Return the pair ``(self.numerator(), self.denominator())``.

        EXAMPLES::

            sage: x = -12/29
            sage: x.as_integer_ratio()
            (-12, 29)
        """

    def factor(self):
        """
        Return the factorization of this rational number.

        OUTPUT: factorization

        EXAMPLES::

            sage: (-4/17).factor()
            -1 * 2^2 * 17^-1

        Trying to factor 0 gives an arithmetic error::

            sage: (0/1).factor()
            Traceback (most recent call last):
            ...
            ArithmeticError: factorization of 0 is not defined
        """

    def support(self):
        """
        Return a sorted list of the primes where this rational number has
        nonzero valuation.

        OUTPUT: the set of primes appearing in the factorization of this
        rational with nonzero exponent, as a sorted list.

        EXAMPLES::

            sage: (-4/17).support()
            [2, 17]

        Trying to find the support of 0 gives an arithmetic error::

            sage: (0/1).support()
            Traceback (most recent call last):
            ...
            ArithmeticError: Support of 0 not defined.
        """

    def log(self, m=None, prec=None):
        """
        Return the log of ``self``.

        INPUT:

        - ``m`` -- the base (default: natural log base e)

        - ``prec`` -- integer (optional); the precision in bits

        OUTPUT:

        When ``prec`` is not given, the log as an element in symbolic
        ring unless the logarithm is exact. Otherwise the log is a
        :class:`RealField` approximation to ``prec`` bit precision.

        EXAMPLES::

            sage: (124/345).log(5)                                                      # needs sage.symbolic
            log(124/345)/log(5)
            sage: (124/345).log(5, 100)                                                 # needs sage.rings.real_mpfr
            -0.63578895682825611710391773754
            sage: log(QQ(125))                                                          # needs sage.symbolic
            3*log(5)
            sage: log(QQ(125), 5)
            3
            sage: log(QQ(125), 3)                                                       # needs sage.symbolic
            3*log(5)/log(3)
            sage: QQ(8).log(1/2)
            -3
            sage: (1/8).log(1/2)
            3
            sage: (1/2).log(1/8)
            1/3
            sage: (1/2).log(8)
            -1/3
            sage: (16/81).log(8/27)                                                     # needs sage.libs.pari
            4/3
            sage: (8/27).log(16/81)                                                     # needs sage.libs.pari
            3/4
            sage: log(27/8, 16/81)                                                      # needs sage.libs.pari
            -3/4
            sage: log(16/81, 27/8)                                                      # needs sage.libs.pari
            -4/3
            sage: (125/8).log(5/2)                                                      # needs sage.libs.pari
            3
            sage: (125/8).log(5/2, prec=53)                                             # needs sage.rings.real_mpfr
            3.00000000000000

        TESTS::

            sage: (25/2).log(5/2)                                                       # needs sage.symbolic
            log(25/2)/log(5/2)
            sage: (-1/2).log(3)                                                         # needs sage.symbolic
            (I*pi + log(1/2))/log(3)
        """

    def gamma(self, *, prec=None):
        """
        Return the gamma function evaluated at ``self``. This value is exact
        for integers and half-integers, and returns a symbolic value
        otherwise.  For a numerical approximation, use keyword ``prec``.

        EXAMPLES::

            sage: # needs sage.symbolic
            sage: gamma(1/2)
            sqrt(pi)
            sage: gamma(7/2)
            15/8*sqrt(pi)
            sage: gamma(-3/2)
            4/3*sqrt(pi)
            sage: gamma(6/1)
            120
            sage: gamma(1/3)
            gamma(1/3)

        This function accepts an optional precision argument::

            sage: (1/3).gamma(prec=100)                                                 # needs sage.rings.real_mpfr
            2.6789385347077476336556929410
            sage: (1/2).gamma(prec=100)                                                 # needs sage.rings.real_mpfr
            1.7724538509055160272981674833

        TESTS:

        This is not the incomplete gamma function! ::

            sage: (1/2).gamma(5)
            Traceback (most recent call last):
            ...
            TypeError: ...gamma() takes exactly 0 positional arguments (1 given)
        """

    def floor(self):
        """
        Return the floor of this rational number as an integer.

        OUTPUT: integer

        EXAMPLES::

            sage: n = 5/3; n.floor()
            1
            sage: n = -17/19; n.floor()
            -1
            sage: n = -7/2; n.floor()
            -4
            sage: n = 7/2; n.floor()
            3
            sage: n = 10/2; n.floor()
            5
        """

    def ceil(self):
        """
        Return the ceiling of this rational number.

        OUTPUT: integer

        If this rational number is an integer, this returns this number,
        otherwise it returns the floor of this number +1.

        EXAMPLES::

            sage: n = 5/3; n.ceil()
            2
            sage: n = -17/19; n.ceil()
            0
            sage: n = -7/2; n.ceil()
            -3
            sage: n = 7/2; n.ceil()
            4
            sage: n = 10/2; n.ceil()
            5
        """

    def trunc(self):
        """
        Round this rational number to the nearest integer toward zero.

        EXAMPLES::

            sage: (5/3).trunc()
            1
            sage: (-5/3).trunc()
            -1
            sage: QQ(42).trunc()
            42
            sage: QQ(-42).trunc()
            -42
        """

    def round(self: Rational, mode='even'):
        """
        Return the nearest integer to ``self``, rounding to even by default.

        INPUT:

        - ``self`` -- a rational number

        - ``mode`` -- a rounding mode for half integers:

           - ``'toward'`` rounds toward zero
           - ``'away'`` (default) rounds away from zero
           - ``'up'`` rounds up
           - ``'down'`` rounds down
           - ``'even'`` rounds toward the even integer
           - ``'odd'`` rounds toward the odd integer

        OUTPUT: integer

        EXAMPLES::

            sage: (9/2).round()
            4
            sage: n = 4/3; n.round()
            1
            sage: n = -17/4; n.round()
            -4
            sage: n = -5/2; n.round()
            -2
            sage: n.round("away")
            -3
            sage: n.round("up")
            -2
            sage: n.round("down")
            -3
            sage: n.round("even")
            -2
            sage: n.round("odd")
            -3
        """

    def real(self):
        """
        Return the real part of ``self``, which is ``self``.

        EXAMPLES::

            sage: (1/2).real()
            1/2
        """

    def imag(self):
        """
        Return the imaginary part of ``self``, which is zero.

        EXAMPLES::

            sage: (1/239).imag()
            0
        """

    def height(self):
        """
        The max absolute value of the numerator and denominator of ``self``, as
        an :class:`Integer`.

        OUTPUT: integer

        EXAMPLES::

            sage: a = 2/3
            sage: a.height()
            3
            sage: a = 34/3
            sage: a.height()
            34
            sage: a = -97/4
            sage: a.height()
            97

        AUTHORS:

        - Naqi Jaffery (2006-03-05): examples

        .. NOTE::

           For the logarithmic height, use :meth:`global_height()`.
        """

    def additive_order(self):
        """
        Return the additive order of ``self``.

        OUTPUT: integer or infinity

        EXAMPLES::

            sage: QQ(0).additive_order()
            1
            sage: QQ(1).additive_order()
            +Infinity
        """

    def multiplicative_order(self):
        """
        Return the multiplicative order of ``self``.

        OUTPUT: integer or ``infinity``

        EXAMPLES::

            sage: QQ(1).multiplicative_order()
            1
            sage: QQ('1/-1').multiplicative_order()
            2
            sage: QQ(0).multiplicative_order()
            +Infinity
            sage: QQ('2/3').multiplicative_order()
            +Infinity
            sage: QQ('1/2').multiplicative_order()
            +Infinity
        """

    def is_one(self):
        """
        Determine if a rational number is one.

        OUTPUT: boolean

        EXAMPLES::

            sage: QQ(1/2).is_one()
            False
            sage: QQ(4/4).is_one()
            True
        """

    def is_integral(self):
        """
        Determine if a rational number is integral (i.e., is in
        `\\ZZ`).

        OUTPUT: boolean

        EXAMPLES::

            sage: QQ(1/2).is_integral()
            False
            sage: QQ(4/4).is_integral()
            True
        """

    def is_rational(self):
        """
        Return ``True`` since this is a rational number.

        EXAMPLES::

            sage: (3/4).is_rational()
            True
        """

    def is_S_integral(self, S=...):
        """
        Determine if the rational number is ``S``-integral.

        ``x`` is ``S``-integral if ``x.valuation(p)>=0`` for all ``p`` not in
        ``S``, i.e., the denominator of ``x`` is divisible only by the primes
        in ``S``.

        INPUT:

        - ``S`` -- list or tuple of primes

        OUTPUT: boolean

        .. NOTE::

           Primality of the entries in ``S`` is not checked.

        EXAMPLES::

            sage: QQ(1/2).is_S_integral()
            False
            sage: QQ(1/2).is_S_integral([2])
            True
            sage: [a for a in range(1,11) if QQ(101/a).is_S_integral([2,5])]
            [1, 2, 4, 5, 8, 10]
        """

    def is_S_unit(self, S=None):
        """
        Determine if the rational number is an ``S``-unit.

        ``x`` is an ``S``-unit if ``x.valuation(p)==0`` for all ``p`` not in
        ``S``, i.e., the numerator and denominator of ``x`` are divisible only
        by the primes in `S`.

        INPUT:

        - ``S`` -- list or tuple of primes

        OUTPUT: boolean

        .. NOTE::

           Primality of the entries in ``S`` is not checked.

        EXAMPLES::

            sage: QQ(1/2).is_S_unit()
            False
            sage: QQ(1/2).is_S_unit([2])
            True
            sage: [a for a in range(1,11) if QQ(10/a).is_S_unit([2,5])]
            [1, 2, 4, 5, 8, 10]
        """

    def __lshift__(x, y):
        """
        Left shift operator ``x << y``.

        INPUT:

        - ``x``, ``y`` -- integer or rational

        OUTPUT: rational

        EXAMPLES::

            sage: (2/3).__lshift__(4/1)
            32/3
            sage: (2/3).__lshift__(4/7)
            Traceback (most recent call last):
            ...
            ValueError: denominator must be 1
            sage: (2).__lshift__(4/1)
            32
            sage: (2/3).__lshift__(4)
            32/3
            sage: (2/3) << (4/1)
            32/3
        """

    def __rshift__(x, y):
        """
        Right shift operator ``x >> y``.

        INPUT:

        - ``x``, ``y`` -- integer or rational

        OUTPUT: rational

        EXAMPLES::

            sage: (2/3).__rshift__(4/1)
            1/24
            sage: (2/3).__rshift__(4/7)
            Traceback (most recent call last):
            ...
            ValueError: denominator must be 1
            sage: (2).__rshift__(4/1)
            0
            sage: (2/1).__rshift__(4)
            1/8
            sage: (2/1) >>(4/1)
            1/8
        """

    def conjugate(self):
        """
        Return the complex conjugate of this rational number, which is
        the number itself.

        EXAMPLES::

            sage: n = 23/11
            sage: n.conjugate()
            23/11
        """

    def __pari__(self):
        """
        Return the PARI version of this rational number.

        EXAMPLES::

            sage: n = 9390823/17
            sage: m = n.__pari__(); m                                                   # needs sage.libs.pari
            9390823/17
            sage: type(m)                                                               # needs sage.libs.pari
            <class 'cypari2.gen.Gen'>
            sage: m.type()                                                              # needs sage.libs.pari
            't_FRAC'
        """

    def _interface_init_(self, I=None):
        """
        Return representation of this rational suitable for coercing into
        almost any computer algebra system.

        OUTPUT: string

        EXAMPLES::

            sage: (2/3)._interface_init_()
            '2/3'
            sage: kash(3/1).Type()              # optional - kash
            elt-fld^rat
            sage: magma(3/1).Type()             # optional - magma
            FldRatElt
        """

    def _sage_input_(self, sib, coerced):
        """
        Produce an expression which will reproduce this value when evaluated.

        EXAMPLES::

            sage: sage_input(QQ(1), verify=True)
            # Verified
            QQ(1)
            sage: sage_input(-22/7, verify=True)
            # Verified
            -22/7
            sage: sage_input(-22/7, preparse=False)
            -ZZ(22)/7
            sage: sage_input(10^-50, verify=True)
            # Verified
            1/100000000000000000000000000000000000000000000000000
            sage: from sage.misc.sage_input import SageInputBuilder
            sage: (-2/37)._sage_input_(SageInputBuilder(preparse=False), False)
            {unop:- {binop:/ {call: {atomic:ZZ}({atomic:2})} {atomic:37}}}
            sage: QQ(5)._sage_input_(SageInputBuilder(preparse=False), True)
            {atomic:5}
        """

class Z_to_Q(Morphism):
    """
    A morphism from `\\ZZ` to `\\QQ`.
    """

    def _call_(self, x) -> Element:
        """
        Return the image of the morphism on ``x``.

        EXAMPLES::

            sage: sage.rings.rational.Z_to_Q()(2) # indirect doctest
            2
        """

    def __init__(self):
        """
        Create morphism from integers to rationals.

        EXAMPLES::

            sage: sage.rings.rational.Z_to_Q()
            Natural morphism:
              From: Integer Ring
              To:   Rational Field
        """

    def section(self):
        """
        Return a section of this morphism.

        EXAMPLES::

            sage: f = QQ.coerce_map_from(ZZ).section(); f
            Generic map:
              From: Rational Field
              To:   Integer Ring

        This map is a morphism in the category of sets with partial
        maps (see :issue:`15618`)::

            sage: f.parent()
            Set of Morphisms from Rational Field to Integer Ring
             in Category of sets with partial maps
        """

    def is_surjective(self):
        """
        Return whether this morphism is surjective.

        EXAMPLES::

            sage: QQ.coerce_map_from(ZZ).is_surjective()
            False
        """

class Q_to_Z(Map):
    """
    A morphism from `\\QQ` to `\\ZZ`.

    TESTS::

        sage: type(ZZ.convert_map_from(QQ))
        <class 'sage.rings.rational.Q_to_Z'>
    """

    def _call_(self, x) -> Element:
        """
        A fast map from the rationals to the integers.

        EXAMPLES::

            sage: f = sage.rings.rational.Q_to_Z(QQ, ZZ)
            sage: f(1/2) # indirect doctest
            Traceback (most recent call last):
            ...
            TypeError: no conversion of this rational to integer
            sage: f(4/2) # indirect doctest
            2
        """

    def section(self):
        """
        Return a section of this morphism.

        EXAMPLES::

            sage: sage.rings.rational.Q_to_Z(QQ, ZZ).section()
            Natural morphism:
              From: Integer Ring
              To:   Rational Field
        """

class int_to_Q(Morphism):
    """
    A morphism from Python 3 ``int`` to `\\QQ`.
    """

    def _call_(self, a) -> Element:
        """
        Return the image of the morphism on ``a``.

        EXAMPLES::

            sage: f = sage.rings.rational.int_to_Q()
            sage: f(4^100)
            1606938044258990275541962092341162602522202993782792835301376
        """

    def __init__(self):
        """
        Initialize ``self``.

        EXAMPLES::

            sage: sage.rings.rational.int_to_Q()
            Native morphism:
              From: Set of Python objects of class 'int'
              To:   Rational Field
        """
RealNumber_classes = ()
RealDouble_classes = (float,)
set_rational_from_gen = None
new_gen_from_rational = None
ai = sage.rings.fast_arith.arith_int()

def integer_rational_power(a: Integer, b: Rational) -> Integer:
    """
    Compute `a^b` as an integer, if it is integral, or return ``None``.

    The nonnegative real root is taken for even denominators.

    INPUT:

    - ``a`` -- an ``Integer``
    - ``b`` -- a nonnegative ``Rational``

    OUTPUT: `a^b` as an ``Integer`` or ``None``

    EXAMPLES::

        sage: from sage.rings.rational import integer_rational_power
        sage: integer_rational_power(49, 1/2)
        7
        sage: integer_rational_power(27, 1/3)
        3
        sage: integer_rational_power(-27, 1/3) is None
        True
        sage: integer_rational_power(-27, 2/3) is None
        True
        sage: integer_rational_power(512, 7/9)
        128

        sage: integer_rational_power(27, 1/4) is None
        True
        sage: integer_rational_power(-16, 1/4) is None
        True

        sage: integer_rational_power(0, 7/9)
        0
        sage: integer_rational_power(1, 7/9)
        1
        sage: integer_rational_power(-1, 7/9) is None
        True
        sage: integer_rational_power(-1, 8/9) is None
        True
        sage: integer_rational_power(-1, 9/8) is None
        True

    TESTS (:issue:`11228`)::

        sage: integer_rational_power(-10, QQ(2))
        100
        sage: integer_rational_power(0, QQ(0))
        1
    """

def rational_power_parts(a, b: Rational, factor_limit=None):
    """
    Compute rationals or integers `c` and `d` such that `a^b = c*d^b`
    with `d` small. This is used for simplifying radicals.

    INPUT:

    - ``a`` -- a rational or integer
    - ``b`` -- a rational
    - ``factor_limit`` -- the limit used in factoring ``a``

    EXAMPLES::

        sage: from sage.rings.rational import rational_power_parts
        sage: rational_power_parts(27, 1/2)
        (3, 3)
        sage: rational_power_parts(-128, 3/4)
        (8, -8)
        sage: rational_power_parts(-4, 1/2)
        (2, -1)
        sage: rational_power_parts(-4, 1/3)
        (1, -4)
        sage: rational_power_parts(9/1000, 1/2)
        (3/10, 1/10)

    TESTS:

    Check if :issue:`8540` is fixed::

        sage: rational_power_parts(3/4, -1/2)
        (2, 3)
        sage: t = (3/4)^(-1/2); t                                                       # needs sage.symbolic
        2/3*sqrt(3)
        sage: t^2                                                                       # needs sage.symbolic
        4/3

    Check if :issue:`15605` is fixed::

        sage: rational_power_parts(-1, -1/3)
        (1, -1)
        sage: rational_power_parts(-1, 2/3)
        (1, -1)
        sage: all(rational_power_parts(-1, i/77) == (1,-1) for i in range(1,9))
        True

        sage: # needs sage.symbolic
        sage: (-1)^(-1/3)
        -(-1)^(2/3)
        sage: 1 / ((-1)^(1/3))
        -(-1)^(2/3)
        sage: (-1)^(2/3)
        (-1)^(2/3)
        sage: (-1)^(1/3)*(-1)^(1/5)
        (-1)^(8/15)
        sage: bool((-1)^(2/3) == -1/2 + sqrt(3)/2*I)
        True
        sage: all((-1)^(p/q) == cos(p*pi/q) + I * sin(p*pi/q)
        ....:     for p in srange(1, 6) for q in srange(1, 6))
        True

    A few more tests added in :issue:`26414`::

        sage: rational_power_parts(-1, 2/1)
        (1, 1)
        sage: rational_power_parts(-8, 2/3)
        (4, -1)
        sage: all(isinstance(z, Integer) for z in rational_power_parts(-1, 1/1))
        True
        sage: all(isinstance(z, Integer) for z in rational_power_parts(-1, 2/3))
        True
    """

def is_Rational(x):
    """
    Return ``True`` if ``x`` is of the Sage :class:`Rational` type.

    EXAMPLES::

        sage: from sage.rings.rational import is_Rational
        sage: is_Rational(2)
        doctest:warning...
        DeprecationWarning: The function is_Rational is deprecated;
        use 'isinstance(..., Rational)' instead.
        See https://github.com/sagemath/sage/issues/38128 for details.
        False
        sage: is_Rational(2/1)
        True
        sage: is_Rational(int(2))
        False
        sage: is_Rational('5')
        False
    """

def make_rational(s):
    """
    Make a rational number from ``s`` (a string in base 32).

    INPUT:

    - ``s`` -- string in base 32

    OUTPUT: rational

    EXAMPLES::

        sage: (-7/15).str(32)
        '-7/f'
        sage: sage.rings.rational.make_rational('-7/f')
        -7/15
    """

# This file was generated by stubgen-pyx v0.2.2 from tools/typing/workspace/sage/rings/rational.pyx