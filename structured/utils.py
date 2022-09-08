"""
Various utility methods.
"""
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
