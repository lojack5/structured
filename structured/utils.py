"""
Various utility methods.
"""
from typing import TypeVar
from .type_checking import _T, NoReturn, Any, Callable


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
        if any((isinstance(arg, (TypeVar, StructuredAlias)) for arg in resolved)):
            # Act as immutable, so create a new instance, since these objects
            # are often cached in type factory indexing methods.
            return StructuredAlias(self.cls, resolved)
        else:
            return self.cls[resolved]
