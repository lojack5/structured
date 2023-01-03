"""
Various utility methods.
"""
import operator
import sys
import warnings
from functools import wraps

from .type_checking import Any, Callable, NoReturn, Optional, ParamSpec, T, TypeVar

if sys.version_info < (3, 10):
    from typing import overload

    from .type_checking import Iterable, S

    @overload
    def zips(iterable1: Iterable[S], *, strict: bool = ...) -> Iterable[tuple[S]]:
        ...

    @overload
    def zips(  # noqa: F811
        iterable1: Iterable[S], iterable2: Iterable[T], *, strict: bool = ...
    ) -> Iterable[tuple[S, T]]:
        ...

    @overload
    def zips(  # noqa: F811
        iterable1: Iterable[Any],
        iterable2: Iterable[Any],
        *iterables: Iterable[Any],
        strict: bool = ...,
    ) -> Iterable[tuple[Any, ...]]:
        ...

    def zips(*iterables: Iterable, strict: bool = False):  # noqa: F811
        """Python 3.9 compatible way of emulating zip(..., strict=True)"""
        if not strict:
            yield from zip(*iterables)
        else:
            iterators = [iter(it) for it in iterables]
            yield from zip(*iterators)
            # Check all consumed:
            for it in iterators:
                try:
                    next(it)
                except StopIteration:
                    pass
                else:
                    raise ValueError('iterables must be of equal length')

else:
    zips = zip


def attrgetter(*attr_names: str) -> Callable[[Any], tuple[Any, ...]]:
    """Create an operator.attrgetter-like callable.  The differences are if no
    attributes are specified, the callable returns and empty tuple, and a single
    attribute supplied still returns the attribute in a tuple.
    """
    if not attr_names:
        return lambda x: ()
    _get = operator.attrgetter(*attr_names)
    if len(attr_names) == 1:
        return lambda x: (_get(x),)
    else:
        return _get


@classmethod
def __error_getitem__(cls: type, _key: Any) -> NoReturn:
    """Cause a helpful error if a class is indexed.  Used by `specialized`."""
    raise TypeError(f'{cls.__qualname__} is already specialized.')


def specialized(base_cls: type, *args: Any) -> Callable[[type[T]], type[T]]:
    """Marks a class as already specialized, overriding the class' indexing
    method with one that raises a helpful error.  Also fixes up the class'
    qualname to be a more readable name.

    :param cls: The class to mark as already specialized.
    :return: The class with described modifications.
    """

    def wrapper(cls: type[T]) -> type[T]:
        setattr(cls, '__class_getitem__', __error_getitem__)
        qualname = ', '.join((getattr(k, '__qualname__', f'{k}') for k in args))
        name = ', '.join((getattr(k, '__name__', f'{k}') for k in args))
        cls.__qualname__ = f'{base_cls.__qualname__}[{qualname}]'
        cls.__name__ = f'{base_cls.__name__}[{name}]'
        return cls

    return wrapper


class StructuredAlias:
    """Class to hold one of the structured types that takes types as arguments,
    which has been passes either another StructuredAlias or a TypeVar.
    """

    cls: type
    args: tuple

    def __init__(self, cls: type, args: tuple[Any, ...]) -> None:
        """Wrap a generic class along with whatever generic arguments it was
        created with.
        """
        self.cls = cls
        self.args = args

    def resolve(self, tvar_map: dict[TypeVar, Any]):
        """Attempt to resolve the specific generic specialization given a map
        of TypeVars to concrete types.  If any TypeVars remain, return a new
        StructuredAlias that can be further resolved.

        :param tvar_map: A map of TypeVars to concrete types.
        :return: The fully specialized class, or a new StructuredAlias
        """
        resolved = []
        for arg in self.args:
            arg = tvar_map.get(arg, arg)
            if isinstance(arg, StructuredAlias):
                arg = arg.resolve(tvar_map)
            resolved.append(arg)
        resolved = tuple(resolved)
        if any((isinstance(arg, (TypeVar, StructuredAlias)) for arg in resolved)):
            # Act as immutable, so create a new instance, since these objects
            # are often cached in type factory indexing methods.
            return StructuredAlias(self.cls, resolved)
        else:
            return self.cls[resolved]  # type: ignore


# nice deprecation warnings, ideas taken from Trio
class StructuredDeprecationWarning(FutureWarning):
    """Warning emitted if you use deprecated Structured functionality. This
    feature will be removed in a future version. Despite the name, this class
    currently inherits from :class:`FutureWarning`, not
    :class:`DeprecationWarning`, because we want these warning to be visible by
    default. You can hide them by installing a filter or with the ``-W``
    switch.
    """


def _stringify(x: Any) -> str:
    """Attempt to make a nice string representation of `x` if possible.

    :param x: Object to stringize, usually a method or class.
    :return: The best human readable string representation of `x` that this
        method can achieve.
    """
    try:
        return f'{x.__module__}.{x.__qualname__}'
    except AttributeError:
        return str(x)


def _issue_url(issue: int) -> str:
    """Generate a uri to the repository issues for a specific issue number.

    :param issue: Issue number to link to.
    :return: The uri to the issue.
    """
    return (
        f'https://github.com/lojack5/structured/issuespython-trio/trio/issues/{issue}'
    )


def warn_deprecated(
    x: Any,
    version: str,
    removal: str,
    *,
    issue: Optional[int],
    use_instead: Any,
    stacklevel: int = 2,
) -> None:
    """Emit a deprecation warning for using object `x`.

    :param x: The object that is being used.
    :param version: Version this object was deprecated.
    :param removal: Version this object will be removed completely.
    :param issue: GitHub issue number mentioning this.
    :param use_instead: Alternative to use instead of `x`.
    :param stacklevel: Stack-frame to have this warning show up in.
    """
    stacklevel += 1
    msg = (
        f'{_stringify(x)} is deprecated since structured-classes {version} '
        f'and will be removed in structured-classes {removal}'
    )
    if use_instead is None:
        msg += ' with no replacement'
    else:
        msg += f'; use {_stringify(use_instead)} instead'
    if issue is not None:
        msg += f' ({_issue_url(issue)})'
    warnings.warn(StructuredDeprecationWarning(msg), stacklevel=stacklevel)


P = ParamSpec('P')
T = TypeVar('T')


def deprecated(
    version: str,
    removal: str,
    *,
    x: Any = None,
    issue: int,
    use_instead: Any,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorate a callable as deprecated.
    Usage:
        @deprecated(version, removal [, issue=..., use_instead=...])
        def deprecated_method(...):
            ...

    :param version: Version the callable was deprecated.
    :param removal: Version the callable will be removed completely.
    :param issue: GitHub issue number mentioning this.
    :param use_instead: Alternative to use instead of the callable.
    :param x: Callable to mark as deprecated.
    :return: The wrapped callable which emits deprecation warning.
    """

    def inner(fn: Callable[P, T]) -> Callable[P, T]:
        nonlocal x

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            warn_deprecated(x, version, removal, use_instead=use_instead, issue=issue)
            return fn(*args, **kwargs)

        # If our __module__ or __qualname__ get modified, we want to pick up
        # on that, so we read them off the wrapper object instead of the (now
        # hidden) fn object
        if x is None:
            x = wrapper

        if wrapper.__doc__ is not None:
            doc = wrapper.__doc__
            doc = doc.rstrip() + f'\n\n .. deprecated:: {version}\n'
            if use_instead is not None:
                doc += f'   Use {_stringify(use_instead)} instead.\n'
            if issue is not None:
                doc += f'   For details, see `issue #{issue} '
                doc += f'<{_issue_url(issue)}>`__.\n'
            doc += '\n'
            wrapper.__doc__ = doc

        return wrapper

    return inner
