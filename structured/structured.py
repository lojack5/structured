from __future__ import annotations

__all__ = [
    'Structured',
    'ByteOrder', 'ByteOrderMode',
]

from functools import reduce
import re

from .base_types import *
from .basic_types import pad
from .type_checking import (
    Any, ClassVar, Optional, ReadableBuffer, SupportsRead, SupportsWrite,
    WritableBuffer, get_type_hints, isclassvar, cast, TypeGuard, Union, TypeVar,
)


_Annotation = Union[format_type, Serializer]

def validate_typehint(attr_type: type) -> TypeGuard[type[_Annotation]]:
    if isclassvar(attr_type):
        return False
    if issubclass(attr_type, requires_indexing):
        raise TypeError(f'{attr_type.__qualname__} must be specialized')
    if issubclass(attr_type, structured_type):
        if issubclass(attr_type, (format_type, Serializer)):
            return True
        else:
            raise TypeError(f'Unknown structured type {attr_type.__qualname__}')
    return False


def filter_typehints(typehints: dict[str, Any]) -> dict[str, type[_Annotation]]:
    return {
        attr: attr_type
        for attr, attr_type in typehints.items()
        if validate_typehint(attr_type)
    }


def split_typehints(
        typehints: dict[str, type[_Annotation]],
    ) -> list[dict[str, type[_Annotation]]]:
    split: list[dict[str, type[_Annotation]]] = []

    current_group = {}
    def finalize_group():
        nonlocal current_group
        if current_group:
            split.append(current_group)
            current_group = {}

    for attr, attr_type in typehints.items():
        if issubclass(attr_type, format_type):
            current_group[attr] = attr_type
        else:   # Serializer
            finalize_group()
            split.append({attr: attr_type})
    finalize_group()
    return split


def create_struct(
        typehints: dict[str, type[format_type]],
        byte_order: ByteOrder,
    ) -> tuple[StructSerializer, tuple[str, ...]]:
    fmt = reduce(fold_overlaps,
                 (var_type.format for var_type in typehints.values())
    )
    attr_actions = {
        attr: attr_type.unpack_action
        for attr, attr_type in typehints.items()
        if not issubclass(attr_type, pad)
    }
    attrs = tuple(attr_actions.keys())
    actions = tuple(attr_actions.values())
    st = struct_cache(byte_order.value + fmt, actions)
    return st, attrs


def create_serializer(
        typehints: dict[str, Any],
        byte_order: ByteOrder,
    ) -> tuple[Serializer, tuple[str, ...]]:
    applicable_hints = filter_typehints(typehints)
    hint_groups = split_typehints(applicable_hints)
    all_attrs: list[str] = []
    # First, generate struct.Struct objects where necessary
    serializers = {}
    for group in hint_groups:
        first_type = next(iter(group.values()))
        slice_start = len(all_attrs)
        if issubclass(first_type, format_type):
            # needs to be handled with a struct.Struct instance
            group = cast(dict[str, type[format_type]], group)
            serializer, attrs = create_struct(group, byte_order)
            slice_stop = slice_start + len(attrs)
            all_attrs.extend(attrs)
        else:
            # A custom serializer is being used
            serializer_type = next(iter(group.values()))
            serializer_type = cast(type[Serializer], serializer_type)
            all_attrs.append(next(iter(group.keys())))
            serializer = serializer_type(byte_order)
            slice_stop = slice_start + 1
        serializers[serializer] = slice(slice_start, slice_stop)
    # Check if we need a compound serializer:
    if len(serializers) == 1:
        serializer = next(iter(serializers.keys()))
    else:
        serializer = CompoundSerializer(serializers)
    return serializer, tuple(all_attrs)


_reOverlap: re.Pattern[str] = re.compile(r'(.*?)(\d+)\D$')
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
        if match := _reOverlap.match(format1):
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


class StructuredMeta(type):
    """Metaclass for Structured subclasses.  Handles computing the format string
    and determining assigned class attributes.  Accepts two metaclass arguments:

    :param byte_order: Allows for adding a byte order specifier to the format
        string for this class.
    :type byte_order: ByteOrder
    """

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
        # See if we're extending a Structured base class
        structured_base = find_structured_superclass(bases)
        if structured_base is not None:
            if (byte_order_mode is ByteOrderMode.STRICT and
                (base_order := structured_base.byte_order) is not byte_order):
                raise ValueError(
                    'Incompatable byte order specifications between class '
                    f'{typename} ({byte_order.name}) and base class '
                    f'{structured_base.__qualname__} ({base_order.name}). '
                    'If this is intentional, use `byte_order_mode=OVERRIDE`.'
                )
        # Now grab the serializer and associated attributes
        serializer, attrs = create_serializer(typehints, byte_order)
        # Setup class variables
        classdict['serializer'] = serializer
        classdict['attrs'] = attrs
        classdict['byte_order'] = byte_order

        # Create the class
        return super().__new__(cls, typename, bases, classdict)  #type: ignore

_C = TypeVar('_C', bound='Structured')
class Structured(metaclass=StructuredMeta):
    """Base class for classes which can be packed/unpacked using Python's
    struct module."""
    __slots__ = ()
    serializer: ClassVar[Serializer]
    attrs: ClassVar[tuple[str, ...]]
    byte_order: ClassVar[ByteOrder]

    def __init__(self, *args, **kwargs):
        # TODO: Create the init function on the fly (ala dataclass) so we can
        # leverage python's error checking for argument names, etc.
        attrs_values = dict(zip(self.attrs, args))
        given = len(args)
        expected = len(self.attrs)
        if given > expected:
            raise TypeError(
                f'{type(self).__qualname__}() takes {expected} positional '
                f'arguments but {given} were given'
            )
        duplicates = set(attrs_values.keys()) & set(kwargs.keys())
        if duplicates:
            raise TypeError(
                f'{duplicates} arguments passed as both positional and keyword.'
            )
        attrs_values |= kwargs
        present = set(attrs_values.keys())
        if (missing := (attr_set := set(self.attrs)) - present):
            raise TypeError(f'missing arguments {missing}')
        elif (extra := present - attr_set):
            raise TypeError(f'unknown arguments for {extra}')

        for attr, value in attrs_values.items():
            setattr(self, attr, value)

    # Method prototypes for type checkers, actual implementations are created
    # by the metaclass.
    def unpack(self, buffer: ReadableBuffer) -> None:
        """Unpack values from the bytes-like `buffer` and assign them to members

        :param buffer: A bytes-like object.
        """
        for attr, value in zip(self.attrs, self.serializer.unpack(buffer)):
            setattr(self, attr, value)

    def unpack_read(self, readable: SupportsRead) -> None:
        """Read data from a file-like object and unpack it into values, assigned
        to this class's attributes.

        :param readable: readable file-like object.
        """
        for attr, value in zip(self.attrs,
                               self.serializer.unpack_read(readable)):
            setattr(self, attr, value)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
        """Unpack values from a `buffer` implementing the buffer protocol
        starting at index `offset`, and assign them to their associated class
        members.

        :param buffer: buffer to unpack from.
        :param offset: position in the buffer to start from.
        """
        for attr, value in zip(self.attrs,
                               self.serializer.unpack_from(buffer, offset)):
            setattr(self, attr, value)

    def pack(self) -> bytes:
        """Pack the class's values according to the format string."""
        return self.serializer.pack(
            *(getattr(self, attr) for attr in self.attrs)
        )

    def pack_write(self, writable: SupportsWrite) -> None:
        """Pack the class's values according to the format string, then write
        the result to a file-like object.

        :param writable: writable file-like object.
        """
        self.serializer.pack_write(
            writable,
            *(getattr(self, attr) for attr in self.attrs)
        )

    def pack_into(self, buffer: WritableBuffer, offset: int = 0):
        """Pack the class's values according to the format string, pkacing the
        result into `buffer` starting at position `offset`.

        :param stream: buffer to pack into.
        :param offset: position in the buffer to start writing data to.
        """
        self.serializer.pack_into(
            buffer,
            offset,
            *(getattr(self, attr) for attr in self.attrs)
        )

    @classmethod
    def create_unpack(cls: type[_C], buffer: ReadableBuffer) -> _C:
        return cls(*cls.serializer.unpack(buffer))

    @classmethod
    def create_unpack_from(
            cls: type[_C],
            buffer: ReadableBuffer,
            offset: int = 0
        ) -> _C:
        return cls(*cls.serializer.unpack_from(buffer, offset))

    @classmethod
    def create_unpack_read(cls: type[_C], readable: SupportsRead) -> _C:
        return cls(*cls.serializer.unpack_read(readable))

    def __str__(self) -> str:
        """Descriptive representation of this class."""
        vals = ', '.join((
            f'{attr}={getattr(self, attr)}'
            for attr in self.attrs
        ))
        return f'{type(self).__name__}({vals})'

    def __eq__(self, other) -> bool:
        if type(other) == type(self):
            return all((
                getattr(self, attr) == getattr(other, attr)
                for attr in self.attrs
            ))
        return NotImplemented
