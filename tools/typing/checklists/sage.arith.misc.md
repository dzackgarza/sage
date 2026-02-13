# Checklist for `sage.arith.misc`

## A. Skeleton provenance
- [x] Stubgen command used: (batch run)
- [x] Stubgen log file path: `tools/typing/logs/sage.arith.misc.log` (implicit)

## B. Export surface
- [x] No `__all__` defined. Exports determined by local definitions (and explicit aliases).
- [x] Aliases:
    - `algdep` = `algebraic_dependency`
    - `GCD` = `gcd`
    - `XGCD` = `xgcd`
    - `prime_factors` = `prime_divisors`
    - `CRT` = `crt`
    - `kronecker` = `kronecker_symbol`

## C. Symbol-by-symbol completion

- [x] `algebraic_dependency` / `algdep`
- [x] `bernoulli`
- [x] `factorial`
- [x] `is_prime`
- [x] `is_pseudoprime`
- [x] `is_prime_power`
- [x] `is_pseudoprime_power`
- [x] `valuation`
- [x] `prime_powers`
- [x] `primes_first_n`
- [x] `eratosthenes`
- [x] `primes`
- [x] `next_prime_power`
- [x] `next_probable_prime`
- [x] `next_prime`
- [x] `previous_prime`
- [x] `previous_prime_power`
- [x] `random_prime`
- [x] `divisors`
- [x] `Sigma` (class) -> `sigma` (instance)
- [x] `gcd` / `GCD`
- [x] `xlcm`
- [x] `xgcd` / `XGCD`
- [x] `xkcd`
- [x] `inverse_mod`
- [x] `get_gcd`
- [x] `get_inverse_mod`
- [x] `power_mod`
- [x] `rational_reconstruction`
- [x] `mqrr_rational_reconstruction`
- [x] `trial_division`
- [x] `factor`
- [x] `radical`
- [x] `prime_divisors` / `prime_factors`
- [x] `odd_part`
- [x] `prime_to_m_part`
- [x] `is_square`
- [x] `is_squarefree`
- [x] `Euler_Phi` (class) -> `euler_phi` (instance)
- [x] `carmichael_lambda`
- [x] `crt` / `CRT`
- [x] `CRT_list`
- [x] `CRT_basis`
- [x] `CRT_vectors`
- [x] `binomial`
- [x] `multinomial`
- [x] `binomial_coefficients`
- [x] `multinomial_coefficients`
- [x] `kronecker_symbol` / `kronecker`
- [x] `legendre_symbol`
- [x] `jacobi_symbol`
- [x] `primitive_root`
- [x] `nth_prime`
- [x] `quadratic_residues`
- [x] `Moebius` (class) -> `moebius`
- [x] `continuant`
- [x] `number_of_divisors`
- [x] `hilbert_symbol`
- [x] `hilbert_conductor`
- [x] `hilbert_conductor_inverse`
- [x] `falling_factorial`
- [x] `rising_factorial`
- [x] `integer_ceil`
- [x] `integer_floor`
- [x] `integer_trunc`
- [x] `two_squares`
- [x] `three_squares`
- [x] `four_squares`
- [x] `sum_of_k_squares`
- [x] `subfactorial`
- [x] `is_power_of_two`
- [x] `differences`
- [x] `sort_complex_numbers_for_display`
- [x] `fundamental_discriminant`
- [x] `squarefree_divisors`
- [x] `dedekind_sum`
- [x] `gauss_sum`
- [x] `dedekind_psi`
- [x] `smooth_part`
- [x] `coprime_part`

## D. Dynamic/conditional behavior
- [x] `get_gcd` and `get_inverse_mod` return functions (bound methods or functions) depending on input.

## E. Internal consistency
- [x] Imports checked.
- [x] Type vars checked.

## F. Review Gate
- [x] Verified syntax.
