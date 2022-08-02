from __future__ import annotations


__author__ = 'lojack5'
__version__ = '1.0'

__all__ = [
    'Structured',
    'ByteOrder', 'ByteOrderMode',
    'int8', 'uint8',
    'int16', 'uint16',
    'int32', 'uint32',
    'int64', 'uint64',
    'float16', 'float32', 'float64',
    'char', 'pascal',
    'pad',
]


from functools import cache, reduce
import inspect
import re
import struct
import typing
from enum import Enum
from typing import Any, Callable, ClassVar, Iterable, Optional

from .type_checking import *


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


class ByteOrderMode(Enum):
    """How derived classes with conflicting byte order markings should function.
    """
    OVERRIDE = 'override'
    STRICT = 'strict'


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


def fold_overlaps(format1: str, format2: str) -> str:
    """Combines two format strings into one, combining common types into counted
    versions, i.e.: 'h' + 'h' -> '2h'.  The format strings must not contain
    byte order specifiers.

    :param format1: First format string to combine, may be empty.
    :param format2: Second format string to combine, may be empty.
    :return: The combined format string.
    """
    if not format1:
        return format2
    elif not format2:
        return format1
    if ((overlap := format1[-1]) == format2[0] and
         overlap not in ('s', 'p')):
        reOverlap = re.compile('(.*?)(\d+)\D')
        if match := reOverlap.match(format1):
            prelude, count = match.groups()
            count = int(count)
        else:
            prelude = format1[:-1]
            count = 1
        count += 1
        format = f'{prelude}{count}{overlap}{format2[1:]}'
    else:
        format = format1 + format2
    return format


def compute_format(
        classname: str,
        typehints: dict[str, Any],
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        globals: dict = {},
        locals: dict = {},
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
        vartype = eval_annotation(vartype, globals, locals)
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
    if fmts:
        return _struct(reduce(fold_overlaps, fmts)), attrs
    else:
        # Special case for the Structured base class
        return None, ()


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
        if qualname := getattr(cls, '__qualname__', None):  # pragma: no branch
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


def eval_annotation(annotation: Any, globalsn, localsn) -> Any:
    if isinstance(annotation, str):
        return eval(annotation, globalsn, localsn)
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
            byte_order: ByteOrder = ByteOrder.DEFAULT,
            byte_order_mode: ByteOrderMode = ByteOrderMode.STRICT,
        ) -> type[Structured]:
        module = sys.modules.get(classdict['__module__'], None)
        globalsn = getattr(module, '__dict__', {})
        st, attrs = compute_format(
            typename, classdict.get('__annotations__', {}), byte_order,
            globalsn, classdict,
        )
        # See if we're extending a Structured base class
        structured_base = cls.find_structured_superclass(bases)
        if structured_base:
            base_struct = structured_base.struct
            base_attrs = structured_base._attrs
            st = cls.merge_formats(
                structured_base.__name__, base_struct,
                typename, st,
                byte_order_mode,
            )
            # Check for duplicate attributes
            if dupes := ', '.join(set(attrs) & set(base_attrs)):
                raise SyntaxError(
                    f'Duplicate structure attributes in class {typename} '
                    f'already defined in base class {structured_base.__name__}:'
                    f' {dupes}.'
                )
            attrs = base_attrs + attrs
        # Enable slots?
        if slots:
            classdict['__slots__'] = attrs
            for attr in attrs:
                classdict.pop(attr, None)
        # Setup class variables
        classdict['struct'] = st
        classdict['_attrs'] = attrs
        # Create the class
        return super().__new__(cls, typename, bases, classdict)

    @staticmethod
    def find_structured_superclass(
        bases: tuple[type],
    ) -> Optional[type[Structured]]:
        """Find any Structured derived base classes, closes to this class in
        the inheritance tree.

        :param bases: Explicitly listed base classes.
        :return: The closest Structured derived base class, or None.
        """
        for chain in bases:
            for base in chain.__mro__:
                # Structured derived, but not Structured itself
                if issubclass(base, Structured) and base is not Structured:
                    return base
        return None

    @classmethod
    def merge_formats(
        cls,
        base_name: str,
        base_struct: struct.Struct,
        derived_name: str,
        derived_struct: struct.Struct,
        mode: ByteOrderMode,
    ) -> struct.Struct:
        """Given two classes' struct instances, combine their structure format
        strings.  If the two strings have differing byte order modes, behavior
        is determined by `mode`: in STRICT, both must match, in OVERRIDE, the
        derived class's byte order mode is used.  Overlapping format specifiers
        are folded, i.e.: 'h10q' + 'qhi' -> 'h11qhi'.

        :param base_name: Base class's name, used for error messages.
        :param base_struct: Base class's struct instance.
        :param derived_name: Derived class's name, used for error messages.
        :param derived_struct: Derived class's struct instance.
        :param mode: How to handle conflicts in byte order mode.
        :raises ValueError: If mode is STRICT and byte_order markers differ.
        :return: A new struct.Struct with the combined format.
        """
        # Extract byte orders
        base_byte_order, base_format = cls.extract_byte_order(
            base_struct.format
        )
        derived_byte_order, derived_format = cls.extract_byte_order(
            derived_struct.format
        )
        if (mode is ByteOrderMode.STRICT and
            base_byte_order is not derived_byte_order):
            raise ValueError(
                'Incompatable byte order specifications between class '
                f'{derived_name} ({derived_byte_order.name}) and base class '
                f'{base_name} ({base_byte_order.name}). If this is intentional,'
                ' use `byte_order_mode=OVERRIDE`.'
            )
        format = fold_overlaps(base_format, derived_format)
        return _struct(derived_byte_order.value + format)


    @staticmethod
    def extract_byte_order(format: str) -> tuple[ByteOrder, str]:
        """Get the byte order marker from a format string, and return it along
        with the format string with the byte order marker removed.

        :param format: A format string for struct.
        :return: The byte order mode and format string without the byte order
            marker.
        """
        if not format:
            return ByteOrder.DEFAULT, ''
        try:
            byte_order = ByteOrder(format[0])
            format = format[1:]
        except ValueError:
            byte_order = ByteOrder.DEFAULT
        return byte_order, format


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
