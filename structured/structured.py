from __future__ import annotations


__author__ = 'lojack5'
__version__ = '1.0'

__all__ = [
    'Structured', 'Formatted',
    'ByteOrder', 'ByteOrderMode',
    'bool8',
    'int8', 'uint8',
    'int16', 'uint16',
    'int32', 'uint32',
    'int64', 'uint64',
    'float16', 'float32', 'float64',
    'char', 'pascal',
    'pad',
]


from functools import cache, reduce
import re
import struct
from enum import Enum

from .type_checking import (
    _T, Any, Callable, ClassVar, Optional, ReadableBuffer, SupportsRead,
    SupportsWrite, WritableBuffer, get_type_hints, is_classvar,
)


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


def noop_action(x: _T) -> _T:
    """Do nothing."""
    return x


class format_type:
    """Base class for annotating types in a Structured subclass."""
    format: ClassVar[str] = ''
    unpack_action: ClassVar[Callable] = noop_action


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


class bool8(int, format_type):
    """bool struct type, stored as an integer."""
    format: ClassVar[str] = '?'


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


class Formatted:
    """Class used for creating new format types.  Provides a class getitem
    to select the format specifier, by grabbing from one of the provided format
    types.  The allowed types may be overridden by overriding cls._types.

    For examples of how to use this, see `TestFormatted`.
    """
    _types: frozenset[format_type] = frozenset()

    @classmethod    # Need to remark as classmethod since we're caching
    @cache
    def __class_getitem__(cls: type[Formatted], key: type) -> type[format_type]:
        if cls._types is Formatted._types:
            # Default, just allow any format type
            if issubclass(key, format_type):
                fmt = key.format
            else:
                raise TypeError(
                    f'Formatted key must be a format_type, got {key!r}.'
                )
        else:
            # Overridden _types, get from that set
            if key not in cls._types:
                raise TypeError(
                    'Formatted key must be one of the allowed types of '
                    f'{cls.__name__}.'
                )
            elif issubclass(key, format_type):
                fmt = key.format
            else:
                raise TypeError(
                    f'Formatted key must be a format_type, got {key!r}.'
                )
        # Create the subclass
        class new_cls(cls, format_type):
            format: ClassVar[str] = fmt
            unpack_action: ClassVar[Callable[[Any], Formatted]]
        if (action := getattr(cls, 'unpack_action', None)) is not None:
            new_cls.unpack_action = action
        else:
            new_cls.unpack_action = new_cls
        new_cls.__qualname__ = f'{cls.__qualname__}[{key.__name__}]'
        return new_cls


class StructuredMeta(type):
    """Metaclass for Structured subclasses.  Handles computing the format string
    and determining assigned class attributes.  Accepts two metaclass arguments:

    :param byte_order: Allows for adding a byte order specifier to the format
        string for this class.
    :type byte_order: ByteOrder
    """
    _reOverlap: ClassVar[re.Pattern[str]] = re.compile(r'(.*?)(\d+)\D$')

    def __new__(
            cls: type[StructuredMeta],
            typename: str,
            bases: tuple[type, ...],
            classdict: dict[str, Any],
            byte_order: ByteOrder = ByteOrder.DEFAULT,
            byte_order_mode: ByteOrderMode = ByteOrderMode.STRICT,
        ) -> type[Structured]:
        # Hacky way to leverage typing.get_type_hints to evaluate stringized
        # annotations, even though the class isn't created yet.  Side benifit
        # is this will also pull in type hints from all base classes as well.
        # This allows for overriding of base class types.
        temp_cls = super().__new__(cls, typename, bases, classdict)
        qualname = temp_cls.__qualname__
        typehints = get_type_hints(temp_cls)
        del temp_cls
        fmt, attr_actions = cls.compute_format(typehints)
        # See if we're extending a Structured base class
        structured_base = cls.find_structured_superclass(bases)
        cls.check_byte_order_conflict(
            structured_base,
            typename,
            byte_order,
            byte_order_mode
        )
        # Setup class variables
        classdict['struct'] = st = cls._struct(byte_order.value + fmt)
        classdict['__format_attrs__'] = tuple(attr_actions.keys())
        cls.gen_packers(qualname, classdict, st, attr_actions)
        cls.gen_unpackers(qualname, classdict, st, attr_actions)
        # Create the class
        return super().__new__(cls, typename, bases, classdict)

    @staticmethod
    @cache
    def _struct(format: str) -> struct.Struct:
        """Cached struct.Struct creation.

        :param format: struct packing format string.
        """
        return struct.Struct(format)

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
    def compute_format(
            cls,
            typehints: dict[str, Any],
        ) -> tuple[str, dict[str, Optional[format_type]]]:
        """Compute a format string and matching attribute names and actions from a
        typehints-like dictionary.

        :param typehints: Mapping of attribute names to type annotations.  Must be
            fully evaluated type hints, not stringized.
        :return: A format string for use with `struct`, as well as a mapping of
            attribute names to any actions needed to apply to them on unpacking.
        """
        fmts: list[str] = ['']
        attr_actions: dict[str, Optional[format_type]] = {}
        for varname, vartype in typehints.items():
            if is_classvar(vartype):
                continue
            elif issubclass(vartype, format_type):
                fmts.append(vartype.format)
                if not issubclass(vartype, pad):
                    attr_actions[varname] = vartype.unpack_action
        return reduce(cls.fold_overlaps, fmts), attr_actions

    @classmethod
    def fold_overlaps(cls, format1: str, format2: str) -> str:
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
            if match := cls._reOverlap.match(format1):
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

    @classmethod
    def check_byte_order_conflict(
        cls,
        base: Optional[type[Structured]],
        derived_name: str,
        derived_byte_order: ByteOrder,
        byte_order_mode: ByteOrderMode,
    ) -> None:
        """Check for byte order conflicts between a base class and derived
        class.

        :param base: base Structured class (if any) for this class.
        :param derived_name: derived class name, used for error messages.
        :param derived_byte_order: derived class ByteOrder specifier.
        :param byte_order_mode: derived class ByteOrderMode.
        :raises ValueError: If a conflict is present.
        """
        if base is not None:
            base_byte_order, _ = cls.extract_byte_order(base.struct.format)
            if (byte_order_mode is ByteOrderMode.STRICT and
                base_byte_order is not derived_byte_order):
                raise ValueError(
                    'Incompatable byte order specifications between class '
                    f'{derived_name} ({derived_byte_order.name}) and base class'
                    f' {base.__name__} ({base_byte_order.name}). If this is '
                    'intentional, use `byte_order_mode=OVERRIDE`.'
                )


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

    @staticmethod
    def gen_packers(
            cls_qualname: str,
            classdict: dict[str, Any],
            struct: struct.Struct,
            attr_actions: dict[str, Callable[[Any], Any]],
        ) -> tuple[
            Callable[[Structured], bytes],
            Callable[[Structured, SupportsWrite], None],
            Callable[[Structured, WritableBuffer, int], None],
        ]:
        """Create packing methods `pack`, `pack_write`, and `pack_into` for a
        Structured class.  We do this in the metaclass for a performance boost
        by bringing some items into local scope of the methods.

        :param cls_qualname: Qualname for the class being created.  Used to set
            the qualname for the generated methods.
        :param classdict: Class dictionary for the created class.
        :param struct: Struct object for the created class.
        :param attr_actions: Mapping of attribute names to actions applied to
            values once unpacked.
        :return: The three generated packing methods.
        """
        packer = struct.pack
        packer_into = struct.pack_into
        attrs = tuple(attr_actions.keys())
        def pack(self) -> bytes:
            """Pack the class's values according to the format string."""
            return packer(*(getattr(self, attr) for attr in attrs))
        def pack_write(self, writable: SupportsWrite) -> None:
            """Pack the class's values according to the format string, then write
            the result to a file-like object.

            :param writable: writable file-like object.
            """
            writable.write(packer(*(getattr(self, attr) for attr in attrs)))
        def pack_into(self, buffer: WritableBuffer, offset: int = 0) -> None:
            """Pack the class's values according to the format string, pkacing the
            result into `buffer` starting at position `offset`.

            :param stream: buffer to pack into.
            :param offset: position in the buffer to start writing data to.
            """
            packer_into(buffer, offset, *(getattr(self, attr) for attr in attrs))
        pack.__qualname__ = cls_qualname + '.pack'
        pack_write.__qualname__ = cls_qualname + '.pack_write'
        pack_into.__qualname__ = cls_qualname = '.pack_into'
        classdict['pack'] = pack
        classdict['pack_write'] = pack_write
        classdict['pack_into'] = pack_into

    @staticmethod
    def gen_unpackers(
            cls_qualname: str,
            classdict: dict[str, Any],
            struct: struct.Struct,
            attr_actions: dict[str, Callable[[Any], Any]],
        ) -> tuple[
            Callable[[Structured, ReadableBuffer], None],
            Callable[[Structured, SupportsRead], None],
            Callable[[Structured, ReadableBuffer, int], None],
        ]:
        """Create unpacking methods `unpack`, `unpack_write`, and `unpack_from`
        for a Structured class.  We do this in the metaclass for a performance
        boost by bringing some items into local scope of the methods.

        :param cls_qualname: Qualname for the class being created.  Used to set
            the qualname for the generated methods.
        :param classdict: Class dictionary for the created class.
        :param struct: Struct object for the created class.
        :param attr_actions: Mapping of attribute names to actions applied to
            values once unpacked.
        :return: The three generated unpacking methods.
        """
        unpacker = struct.unpack
        unpacker_from = struct.unpack_from
        size = struct.size
        custom_unpackers = any((action is not noop_action
                                for action in attr_actions.values()))
        if custom_unpackers:
            attr_actions = tuple(attr_actions.items())
            def unpack(self, buffer: ReadableBuffer) -> None:
                for (attr, action), value in zip(attr_actions,
                                                 unpacker(buffer)):
                    setattr(self, attr, action(value))
            def unpack_read(self, readable: SupportsRead) -> None:
                for (attr, action), value in zip(attr_actions,
                                                 unpacker(readable.read(size))):
                    setattr(self, attr, action(value))
            def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
                for (attr, action), value in zip(attr_actions,
                                                 unpacker_from(buffer, offset)):
                    setattr(self, attr, action(value))
        else:
            # No custom unpackers, so we can optimize a little
            attrs = tuple(attr_actions.keys())
            def unpack(self, buffer: ReadableBuffer) -> None:
                for attr, value in zip(attrs, unpacker(buffer)):
                    setattr(self, attr, value)
            def unpack_read(self, readable: SupportsRead) -> None:
                for attr, value in zip(attrs, unpacker(readable.read(size))):
                    setattr(self, attr, value)
            def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
                for attr, value in zip(attrs, unpacker_from(buffer, offset)):
                    setattr(self, attr, value)
        unpack.__qualname__ = cls_qualname + '.unpack'
        unpack.__doc__ = """
            Unpack values from `stream` according to this class's format string,
            and assign them to their associated class members.

            :param stream: `.read`able stream to draw data from.
            """
        unpack_read.__qualname__ = cls_qualname + '.unpack_read'
        unpack_read.__doc__ = """
            Read data from a file-like object and unpack it into values, assigned
            to this class's attributes.

            :param readable: readable file-like object.
            """
        unpack_from.__qualname__ = cls_qualname + '.unpack_from'
        unpack_from.__doc__ = """
            Unpack values from a `buffer` implementing the buffer protocol
            starting at index `offset`, and assigne them to their associated class
            members.

            :param buffer: buffer to unpack from.
            :param offset: position in the buffer to start from.
            """
        classdict['unpack'] = unpack
        classdict['unpack_read'] = unpack_read
        classdict['unpack_from'] = unpack_from


class Structured(metaclass=StructuredMeta):
    """Base class for classes which can be packed/unpacked using Python's
    struct module."""
    __slots__ = ()
    struct: ClassVar[struct.Struct]
    __format_attrs__: ClassVar[dict[str, Callable]]

    # Method prototypes for type checkers, actual implementations are created
    # by the metaclass.
    def unpack(self, stream: ReadableBuffer) -> None:
        """Unpack values from `stream` according to this class's format string,
        and assign them to their associated class members.

        :param stream: `.read`able stream to draw data from.
        """
    def unpack_read(self, readable: SupportsRead) -> None:
        """Read data from a file-like object and unpack it into values, assigned
        to this class's attributes.

        :param readable: readable file-like object.
        """
    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
        """Unpack values from a `buffer` implementing the buffer protocol
        starting at index `offset`, and assigne them to their associated class
        members.

        :param buffer: buffer to unpack from.
        :param offset: position in the buffer to start from.
        """
    def pack(self) -> bytes:
        """Pack the class's values according to the format string."""
    def pack_write(self, writable: SupportsWrite) -> None:
        """Pack the class's values according to the format string, then write
        the result to a file-like object.

        :param writable: writable file-like object.
        """
    def pack_into(self, buffer: WritableBuffer, offset: int = 0):
        """Pack the class's values according to the format string, pkacing the
        result into `buffer` starting at position `offset`.

        :param stream: buffer to pack into.
        :param offset: position in the buffer to start writing data to.
        """

    def __str__(self) -> str:
        """Descriptive representation of this class."""
        vals = ', '.join((
            f'{attr}={getattr(self, attr)}'
            for attr in self.__format_attrs__
        ))
        return f'{type(self).__name__}({vals})'
