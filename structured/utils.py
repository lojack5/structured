"""
Various utility methods.
"""
from inspect import isclass

from .type_checking import _T, NoReturn, Any, Callable


@classmethod
def __error_getitem__(cls: type, _key: Any) -> NoReturn:
    raise TypeError(f'{cls.__qualname__} is already specialized.')


def specialized(base_cls: type, key: Any) -> Callable[[type[_T]], type[_T]]:
    """Marks a class as already specialized, overriding the class' indexing
    method with one that raises a helpful error.  Also fixes up the class'
    qualname to be a more readable name.

    :param cls: The class to mark as already specialized.
    :return: The class with described modifications.
    """
    def wrapper(cls: type[_T]) -> type[_T]:
        cls.__class_getitem__ = __error_getitem__   # type: ignore
        if isclass(key):
            keyname = key.__qualname__
        else:
            keyname = f'{key}'
        cls.__qualname__ = f'{base_cls.__qualname__}[{keyname}]'
        return cls
    return wrapper
