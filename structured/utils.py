"""
Various utility methods.
"""
import warnings
from typing import ParamSpec, TypeVar
from functools import wraps
from .type_checking import _T, NoReturn, Any, Callable, Optional


@classmethod
def __error_getitem__(cls: type, _key: Any) -> NoReturn:
    raise TypeError(f'{cls.__qualname__} is already specialized.')


def specialized(base_cls: type, *args: Any) -> Callable[[type[_T]], type[_T]]:
    """Marks a class as already specialized, overriding the class' indexing
    method with one that raises a helpful error.  Also fixes up the class'
    qualname to be a more readable name.

    :param cls: The class to mark as already specialized.
    :return: The class with described modifications.
    """
    def wrapper(cls: type[_T]) -> type[_T]:
        setattr(cls, '__class_getitem__', __error_getitem__)
        qualname = ', '.join((
            getattr(k, '__qualname__', f'{k}')
            for k in args
        ))
        name = ', '.join((
            getattr(k, '__name__', f'{k}')
            for k in args
        ))
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

    def __init__(self, cls, args):
        self.cls = cls
        self.args = args

    def resolve(self, tvar_map: dict[TypeVar, type]):
        resolved = []
        for arg in self.args:
            arg = tvar_map.get(arg, arg)
            if isinstance(arg, StructuredAlias):
                arg = arg.resolve(tvar_map)
            resolved.append(arg)
        resolved = tuple(resolved)
        if any((
                isinstance(arg, (TypeVar, StructuredAlias))
                for arg in resolved
            )):
            # Act as immutable, so create a new instance, since these objects
            # are often cached in type factory indexing methods.
            return StructuredAlias(self.cls, resolved)
        else:
            return self.cls[resolved]   # type: ignore


# nice deprecation warnings, ideas from Trio
class StructuredDeprecationWarning(FutureWarning):
    """Warning emitted if you use deprecated Structured functionality. This
    feature will be removed in a future version. Despite the name, this class
    currently inherits from :class:`FutureWarning`, not
    :class:`DeprecationWarning`, because we want these warning to be visible by
    default. You can hide them by installing a filter or with the ``-W``
    switch.
    """


def _stringify(x: Any) -> str:
    if hasattr(x, '__module__') and hasattr(x, '__qualname__'):
        return f'{x.__module__}.{x.__qualname__}'
    else:
        return str(x)

def _issue_url(issue: int) -> str:
    return f'https://github.com/lojack5/structured/issuespython-trio/trio/issues/{issue}'

def warn_deprecated(x: Any, version: str, *, issue: Optional[int], use_instead: Any, stacklevel: int = 2) -> None:
    stacklevel += 1
    msg = f'{_stringify(x)} is deprecated since Structured {version}'
    if use_instead is None:
        msg += ' with no replacement'
    else:
        msg += f'; use {_stringify(use_instead)} instead'
    if issue is not None:
        msg += f' ({_issue_url(issue)})'
    warnings.warn(StructuredDeprecationWarning(msg), stacklevel=stacklevel)


P = ParamSpec('P')
T = TypeVar('T')
# @deprecated("0.2.0", issue=..., use_instead=...)
def deprecated(version: str, *, x: Any = None, issue: int, use_instead: Any) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def inner(fn: Callable[P, T]) -> Callable[P, T]:
        nonlocal x

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            warn_deprecated(x, version, use_instead=use_instead, issue=issue)
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
                doc += f'   For details, see `issue #{issue} <{_issue_url(issue)}>`__.\n'
            doc += '\n'
            wrapper.__doc__ = doc

        return wrapper
    return inner
