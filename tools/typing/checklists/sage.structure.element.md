# Checklist for sage.structure.element

## A. Skeleton Provenance
- [x] Generator: stubgen-pyx
- [x] Log path: `tools/typing/logs/sage.structure.element.log`
- [x] Parsing status: Success

## B. Export Surface
- [x] Method:
    - [x] `__all__` (not present)
    - [x] `__init__` imports
    - [x] source reading
- [x] Exports verified:
    - make_element
    - is_Element
    - Element
    - is_ModuleElement
    - ElementWithCachedMethod
    - ModuleElement
    - ModuleElementWithMutability
    - is_MonoidElement
    - MonoidElement
    - is_AdditiveGroupElement
    - AdditiveGroupElement
    - is_MultiplicativeGroupElement
    - MultiplicativeGroupElement
    - is_RingElement
    - RingElement
    - is_CommutativeRingElement
    - CommutativeRingElement
    - Expression
    - Vector
    - is_Vector
    - Matrix
    - is_Matrix
    - is_IntegralDomainElement
    - IntegralDomainElement
    - is_DedekindDomainElement
    - DedekindDomainElement
    - is_PrincipalIdealDomainElement
    - PrincipalIdealDomainElement
    - is_EuclideanDomainElement
    - EuclideanDomainElement
    - is_FieldElement
    - FieldElement
    - is_AlgebraElement
    - AlgebraElement
    - is_CommutativeAlgebraElement
    - CommutativeAlgebraElement
    - is_InfinityElement
    - InfinityElement
    - canonical_coercion
    - bin_op
    - coercion_model
    - get_coercion_model
    - coercion_traceback
    - coerce_binop

## C. Symbol-by-Symbol Completion
- [x] Completed all classes and functions with types derived from source.

## D. Dynamic/Conditional Behavior
- [x] Checked for runtime attributes
- [x] Checked for conditional imports

## E. Internal Consistency
- [x] `python -m py_compile typings/sage/structure/element.pyi` passed
- [x] Imports are valid or guarded

## F. Review Gate
- [x] Reviewer: Jules
- [x] Date: 2024-05-22
