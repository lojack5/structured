from __future__ import annotations


__author__ = 'lojack5'
__version__ = '1.0'

__all__ = [
    'Structured',
    'ByteOrder', 'ByteOrderMode',
]


from functools import cache, reduce
import re
import struct
from enum import Enum

from .base_types import noop_action, format_type
from .basic_types import pad
from .type_checking import (
    _T, Any, Callable, ClassVar, Optional, ReadableBuffer, SupportsRead,
    SupportsWrite, WritableBuffer, get_type_hints, isclassvar,
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
        cls.gen_packers(classdict, st, attr_actions)
        cls.gen_unpackers(classdict, st, attr_actions)
        # Create the class
        return super().__new__(cls, typename, bases, classdict)  #type: ignore

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

    @classmethod
    def compute_format(
            cls,
            typehints: dict[str, Any],
        ) -> tuple[str, dict[str, Callable[[Any], Any]]]:
        """Compute a format string and matching attribute names and actions from a
        typehints-like dictionary.

        :param typehints: Mapping of attribute names to type annotations.  Must be
            fully evaluated type hints, not stringized.
        :return: A format string for use with `struct`, as well as a mapping of
            attribute names to any actions needed to apply to them on unpacking.
        """
        fmts: list[str] = ['']
        attr_actions: dict[str, Callable[[Any], Any]] = {}
        for varname, vartype in typehints.items():
            if isclassvar(vartype):
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
            classdict: dict[str, Any],
            struct: struct.Struct,
            attr_actions: dict[str, Callable[[Any], Any]],
        ) -> None:
        """Create packing methods `pack`, `pack_write`, and `pack_into` for a
        Structured class.  We do this in the metaclass for a performance boost
        by bringing some items into local scope of the methods.

        :param cls_qualname: Qualname for the class being created.  Used to set
            the qualname for the generated methods.
        :param classdict: Class dictionary for the created class.
        :param struct: Struct object for the created class.
        :param attr_actions: Mapping of attribute names to actions applied to
            values once unpacked.
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
        # Only assign methods that don't have an implementation
        cls_qualname = classdict['__qualname__']
        for method in (pack, pack_write, pack_into):
            method.__qualname__ = cls_qualname + '.' + method.__name__
            classdict.setdefault(method.__name__, method)

    @staticmethod
    def gen_unpackers(
            classdict: dict[str, Any],
            struct: struct.Struct,
            attr_actions: dict[str, Callable[[Any], Any]],
        ) -> None:
        """Create unpacking methods `unpack`, `unpack_write`, and `unpack_from`
        for a Structured class.  We do this in the metaclass for a performance
        boost by bringing some items into local scope of the methods.

        :param cls_qualname: Qualname for the class being created.  Used to set
            the qualname for the generated methods.
        :param classdict: Class dictionary for the created class.
        :param struct: Struct object for the created class.
        :param attr_actions: Mapping of attribute names to actions applied to
            values once unpacked.
        """
        unpacker = struct.unpack
        unpacker_from = struct.unpack_from
        size = struct.size
        custom_unpackers = any((action is not noop_action
                                for action in attr_actions.values()))
        if custom_unpackers:
            actions = tuple(attr_actions.items())
            def unpack(self, buffer: ReadableBuffer) -> None:
                for (attr, action), value in zip(actions, unpacker(buffer)):
                    setattr(self, attr, action(value))
            def unpack_read(self, readable: SupportsRead) -> None:
                for (attr, action), value in zip(actions,
                                                 unpacker(readable.read(size))):
                    setattr(self, attr, action(value))
            def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
                for (attr, action), value in zip(actions,
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
        unpack.__doc__ = """
            Unpack values from `stream` according to this class's format string,
            and assign them to their associated class members.

            :param stream: `.read`able stream to draw data from.
            """
        unpack_read.__doc__ = """
            Read data from a file-like object and unpack it into values, assigned
            to this class's attributes.

            :param readable: readable file-like object.
            """
        unpack_from.__doc__ = """
            Unpack values from a `buffer` implementing the buffer protocol
            starting at index `offset`, and assigne them to their associated class
            members.

            :param buffer: buffer to unpack from.
            :param offset: position in the buffer to start from.
            """
        # Only set the methods if the subclass did not provide an override.
        cls_qualname = classdict['__qualname__']
        for method in (unpack, unpack_read, unpack_from):
            method.__qualname__ = cls_qualname + '.' + method.__name__
            classdict.setdefault(method.__name__, method)


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
        return b''      # pragma: no cover
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
