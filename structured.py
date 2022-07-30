from __future__ import annotations

import array
import ctypes
import inspect
import itertools
import mmap
import pickle
import struct
import sys
import typing
from enum import Enum
from functools import cache
from typing import Any, Callable, ClassVar, Iterable, TypeAlias


__all__ = [
    'Structured',
    'ByteOrder',
    'int8', 'uint8',
    'int16', 'uint16',
    'int32', 'uin32',
    'int64', 'uint64',
    'float6', 'float32', 'float64',
    'char', 'pascal',
    'pad',
]


ReadOnlyBuffer: TypeAlias = bytes
# Anything that implements the read-write buffer interface.
# The buffer interface is defined purely on the C level, so we cannot define a
# normal Protocol for it (until PEP 688 is implemented). Instead we have to list
# the most common stdlib buffer classes in a Union.
if sys.version_info >= (3, 8):
    WriteableBuffer: TypeAlias = (
        bytearray | memoryview | array.array[Any] | mmap.mmap | ctypes._CData |
        pickle.PickleBuffer
    )
else:
    WriteableBuffer: TypeAlias = (  # type: ignore
        bytearray | memoryview | array.array[Any] | mmap.mmap | ctypes._CData
    )
ReadableBuffer: TypeAlias = ReadOnlyBuffer | WriteableBuffer


class ByteOrder(Enum):
    """Byte order specifiers for passing to the struct module.  See the stdlib
    documentation for details on what each means.
    """
    DEFAULT = ''
    LITTLE_ENDIAN = '<'
    LE = LITTLE_ENDIAN
    BIG_ENDIAN = '>'
    BE = BIG_ENDIAN
    NATIVE_STANDARD = '='
    NATIVE_NATIVE = '@'
    NETWORK = '!'


class format_type:
    """Base class for annotating types in a Structured subclass."""
    format: ClassVar[str] = ''


def is_classvar(annotation: Any) -> bool:
    """Determine if a type annotations is for a class variable.

    :param annotation: Fully resolved type annotation to test.
    """
    return (annotation is ClassVar or
            type(annotation) is typing._GenericAlias
            and annotation.__origin__ is ClassVar)


@cache
def _struct(format: str) -> struct.Struct:
    """Cached struct.Struct creation.

    :param format: struct packing format string.
    """
    return struct.Struct(format)


def compute_format(
        classname: str,
        typehints: dict[str, Any],
        byte_order: ByteOrder = ByteOrder.DEFAULT,
    ) -> tuple[struct.Struct, tuple[str, ...]]:
    """Create a struct.Struct object and matching attribute names from a
    type hints dictionary.  Ignores private members (those beginning with '_').

    :param classname: Class name for use in error messages.
    :param typehints: Mapping of attribute names to type annotations.  Can be
        retrieved either from typing.get_type_hints or cls.__annotations__.
    :param byte_order: Any byte order specifiers to add to the format string.
    :raises TypeError: If any annotations are not a subclass of format_type.
    :return: A struct.Struct instance for packing and unpacking data, as well
        as the attribute names to pair the values with.
    """
    fmts: list[str] = [byte_order.value]
    attrs: list[str] = []
    for varname, vartype in typehints.items():
        vartype = eval_annotation(None, vartype)
        if is_classvar(vartype):
            continue
        elif issubclass(vartype, format_type):
            fmts.append(vartype.format)
            if not issubclass(vartype, pad):
                attrs.append(varname)
        elif not varname[0] == '_':
            raise TypeError(
                f'Public member {classname}.{varname} must be of the provided '
                'structured.* types.')
    # Fold repeated format specifiers (except for 's', and 'p')
    return _struct(''.join((
        fmt if (not fmt or fmt[-1] in ('s', 'p')
                or (count := len(list(iterable))) == 1)
        else f'{count}{fmt}'
        for fmt, iterable in itertools.groupby(fmts)
    ))), attrs


class counted(format_type):
    """Base class for string format types.  Allows for specifying the count for
    these types.
    """
    def __class_getitem__(cls: type[counted], count: int) -> type[counted]:
        if not isinstance(count, int):
            raise TypeError('count must be an integer.')
        if count <= 0:
            raise ValueError('count must be positive.')
        class _counted(cls):
            format: ClassVar[str] = f'{count}{cls.format}'
        if qualname := getattr(cls, '__qualname__', None):
            _counted.__qualname__ = f'{qualname}[{count}]'
        return _counted


class pad(counted):
    """Represents one (or more, via pad[x]) padding bytes in the format string.
    Padding bytes are discarded when read, and are written zeroed out.
    """
    format: ClassVar[str] = 'x'

class int8(int, format_type):
    """8-bit signed integer."""
    format: ClassVar[str] = 'b'


class uint8(int, format_type):
    """8-bit unsigned integer."""
    format: ClassVar[str] = 'B'


class int16(int, format_type):
    """16-bit signed integer.""" 
    format: ClassVar[str] = 'h'


class uint16(int, format_type):
    """16-bit unsigned integer."""
    format: ClassVar[str] = 'H'


class int32(int, format_type):
    """32-bit signed integer."""
    format: ClassVar[str] = 'i'


class uint32(int, format_type):
    """32-bit unsigned integer."""
    format: ClassVar[str] = 'I'


class int64(int, format_type):
    """64-bit signed integer."""
    format: ClassVar[str] = 'q'


class uint64(int, format_type):
    """64-bit unsigned integer."""
    format: ClassVar[str] = 'Q'


class float16(float, format_type):
    """IEEE 754 16-bit half-precision floating point number."""
    format: ClassVar[str] = 'e'


class float32(float, format_type):
    """IEEE 754 32-bit floating point number."""
    format: ClassVar[str] = 'f'


class float64(float, format_type):
    """IEEE 754 64-bit double-precision floating point number."""
    format: ClassVar[str] = 'd'


class char(str, counted):
    """String format specifier (bytes in Python).  See 's' in the stdlib struct
    documentation for specific details.
    """
    format: ClassVar[str] = 's'


class pascal(str, counted):
    """String format specifier (bytes in Python).  See 'p' in the stdlib struct
    documentation for specific details.
    """
    format: ClassVar[str] = 'p'


def eval_annotation(method: Callable, annotation: Any) -> Any:
    """Evaluate stringized type annotations on method.  This occurs if
    `from __future__ import annotations` is used, or on python versions
    past 3.10.

    In most cases, typing.get_type_hints should be used instead.  However,
    in the case of a metaclass, the class we want to get type hints for has
    not been created yet, so we have to do this ourselves.

    :param method: For evaluating type hints on a method, that method may have
        been defined within an inner scope.  Providing the method allows for
        grabbing annotations that where defined within that scope.
    :param annotation: The type annotation to evaluate.
    :return: The resolved type annotation.
    """
    if isinstance(annotation, str):
        locals = None
        globals = getattr(method, '__globals__', None)
        method = inspect.unwrap(method)
        globals = getattr(method, '__globals__', globals)
        locals = getattr(method, '__locals__', locals)
        return eval(annotation, globals, locals)
    else:
        return annotation


class StructuredMeta(type):
    """Metaclass for Structured subclasses.  Handles computing the format string
    and determining assigned class attributes.  Accepts two metaclass arguments:

    :param slots: Whether the class should use slots for the assigned attributes.
        NOTE: this only applies to attributes detected as associated with the
        struct format string, so this will not work if the class has other
        (private) members.
    :type: slots: bool
    :param byte_order: Allows for adding a byte order specifier to the format
        string for this class.
    :type byte_order: ByteOrder
    """
    def __new__(
            cls: type[StructuredMeta],
            typename: str,
            bases: tuple[type, ...],
            classdict: dict[str, Any],
            slots: bool = False,
            byte_order: ByteOrder = ByteOrder.DEFAULT
        ) -> type[Structured]:
        st, attrs = compute_format(
            typename, classdict.get('__annotations__', {}), byte_order
        )
        # Enable slots?
        if slots:
            classdict['__slots__'] = attrs
            for attr in attrs:
                del classdict[attr]
        # Setup class variables
        classdict['struct'] = st
        classdict['_attrs'] = attrs
        # Create the class
        return super().__new__(cls, typename, bases, classdict)


class Structured(metaclass=StructuredMeta, slots=True):
    """Base class for classes which can be packed/unpacked using Python's
    struct module."""
    struct: ClassVar[struct.Struct]
    _attrs: ClassVar[tuple[str, ...]]

    def _set(self, values: Iterable[Any]) -> None:
        """Assigns class members' values.

        :param values: Sequence of values in the same order as the attributes
            they should be assigned to.  Attribute order is stored in _attrs.
        """
        for attr, value in zip(self._attrs, values):
            setattr(self, attr, value)

    def _get(self) -> Iterable[Any]:
        """Create an iterable of values to pack with.  Attribute order these
        values are retrived from is stored in _attrs.
        """
        return (getattr(self, attr) for attr in self._attrs)

    def unpack(self, stream: ReadableBuffer) -> None:
        """Unpack values from `stream` according to this class's format string,
        and assign them to their associated class members.

        :param stream: `.read`able stream to draw data from.
        """
        self._set(self.struct.unpack(stream))

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
        """Unpack values from a `buffer` implementing the buffer protocol
        starting at index `offset`, and assigne them to their associated class
        members.

        :param buffer: buffer to unpack from.
        :param offset: position in the buffer to start from.
        """
        self._set(self.struct.unpack_from(buffer, offset))

    def pack(self) -> bytes:
        """Pack the class's values according to the format string."""
        return self.struct.pack(*self._get())

    def pack_into(self, buffer: WriteableBuffer, offset: int = 0):
        """Pack the class's values according to the format string, pkacing the
        result into `buffer` starting at position `offset`.

        :param stream: buffer to pack into.
        :param offset: position in the buffer to start writing data to.
        """
        self.struct.pack_into(buffer, offset, *self._get())

    def __str__(self) -> str:
        """Descriptive representation of this class."""
        vals = ', '.join((f'{attr}={getattr(self, attr)}' for attr in self._attrs))
        return f'{type(self).__name__}({vals})'


if __name__ == '__main__':
    class A(Structured):
        byte: int8 = 0
        byte2: int8 = 0
        bigger: int16 = 0
        _: pad[2] = 0
        hello: char[5] = 'test!'

    print(A.struct.format)
    dat = A.struct.pack(16, 12, 32, b'hello')
    print(repr(dat))
    a = A()
    a.unpack(dat)
    import sys
    print(a)
    print(sys.getsizeof(a))
