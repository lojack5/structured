from __future__ import annotations

__all__ = [
    'StructSerializer',
    'StructActionSerializer',
    'noop_action',
]

import re
import struct
from functools import cached_property, partial, reduce
from itertools import chain, repeat
from typing import overload

from ..base_types import ByteOrder
from ..type_checking import (
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Generic,
    ReadableBuffer,
    Self,
    Ss,
    T,
    Ts,
    Unpack,
)
from .api import Serializer


def noop_action(x: T) -> T:
    """A noop for StructActionSerializers where no additional wrapping is
    needed.
    """
    return x


_struct_chars = r'xcbB\?hHiIlLqQnNefdspP'
_re_end: re.Pattern[str] = re.compile(rf'(.*?)(\d*)([{_struct_chars}])$')
_re_start: re.Pattern[str] = re.compile(rf'^(\d*)([{_struct_chars}])(.*?)')


def fold_overlaps(format1: str, format2: str, combine_strings: bool = False) -> str:
    """Combines two format strings into one, combining common types into counted
    versions, i.e.: 'h' + 'h' -> '2h'.  The format strings must not contain
    byte order specifiers.

    :param format1: First format string to combine, may be empty.
    :param format2: Second format string to combine, may be empty.
    :return: The combined format string.
    """
    start2 = _re_start.match(format2)
    end1 = _re_end.match(format1)
    if start2 and end1:
        prelude, count1, overlap1 = end1.groups()
        count2, overlap2, epilogue = start2.groups()
        if overlap1 == overlap2 and (combine_strings or overlap1 not in ('s', 'p')):
            count1 = int(count1) if count1 else 1
            count2 = int(count2) if count2 else 1
            return f'{prelude}{count1 + count2}{overlap1}{epilogue}'
    return format1 + format2

def split_byte_order(format: str) -> tuple[ByteOrder, str]:
    if format:
        try:
            return ByteOrder(format[0]), format[1:]
        except ValueError:
            pass
    return ByteOrder.DEFAULT, format


class StructSerializer(Generic[Unpack[Ts]], struct.Struct, Serializer[Unpack[Ts]]):
    """A Serializer that is a thin wrapper around struct.Struct, class creation
    is cached.
    """

    _instance_cache: ClassVar[dict[Any, StructSerializer]] = {}

    def __new__(cls, *args, **kwargs) -> Self:
        # Simple caching of creation.  Doesn't do any processing to detect
        # equivalent arguments
        key = tuple(chain(args, sorted(kwargs.items())))
        if cached := cls._instance_cache.get(key, None):
            return cached
        else:
            new_instance = super().__new__(cls)
            cls._instance_cache[key] = new_instance
            # __init__ is called automatically
            return new_instance

    @property
    def byte_order(self) -> ByteOrder:
        return self._split_format[0]

    @property
    def base_format(self) -> str:
        return self._split_format[1]

    @cached_property
    def _split_format(self) -> tuple[ByteOrder, str]:
        return split_byte_order(self.format)

    def __init__(
        self,
        format: str,
        num_values: int = 1,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
    ) -> None:
        """Create a struct.Struct based Serializer

        :param format: Format string.
        :param num_values: Number of values which will be packed/unpacked by
            this Serializer.
        :param byte_order: ByteOrder marking for the format string.
        """
        super().__init__(byte_order.value + format)
        self.num_values = num_values

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.format}, {self.num_values})'

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        else:
            return StructSerializer(fmt, self.num_values, byte_order)

    def unpack(self, buffer: ReadableBuffer) -> tuple[Unpack[Ts]]:
        return super().unpack(buffer[: self.size])  # type: ignore

    def unpack_read(self, readable: BinaryIO) -> tuple[Unpack[Ts]]:
        # NOTE: use super-class's unpack to not interfere with custom
        # logic in subclasses
        return super().unpack(readable.read(self.size))  # type: ignore

    def pack_write(self, writable: BinaryIO, *values: Unpack[Ts]) -> None:
        # NOTE: Call the super-class's pack, so we don't interfere with
        # any custom logic in pack_write for subclasses
        writable.write(super().pack(*values))

    @overload
    def __add__(
        self, other: StructSerializer[Unpack[Ss]]
    ) -> StructSerializer[Unpack[Ts], Unpack[Ss]]:
        ...

    @overload
    def __add__(
        self, other: Serializer[Unpack[Ss]]
    ) -> Serializer[Unpack[Ts], Unpack[Ss]]:
        ...

    def __add__(self, other: Serializer) -> Serializer:
        if isinstance(other, StructSerializer):
            # Don't need a CompoundSerializer for joining with another Struct
            byte_order, lfmt = self._split_format
            byte_order2, rfmt = other._split_format
            # TODO: Check for conflict in byte_order, byte_order2?
            return StructSerializer(
                fold_overlaps(lfmt, rfmt),
                self.num_values + other.num_values,
                byte_order,
            )
        return super().__add__(other)

    def __mul__(self, other: int) -> StructSerializer:  # no tool to hint this yet
        """Return a new StructSerializer that unpacks `other` copies of the
        kine this one does.  I.e: for non-string types it puts a multiplier
        number in front of the format specifier, for strings it repeats the
        format specifier.
        """
        return self._mul_impl(other)

    def __matmul__(self, other: int) -> StructSerializer:
        """Return a new StructSerializer that folds strings together when
        multiplying.  NOTE: This is only supported for StructSerializers that
        consist of either a 's', 'p', or 'x' format specifier.
        """
        return self._mul_impl(other, True)

    def _mul_impl(self, other: int, combine_strings: bool = False) -> StructSerializer:
        if not isinstance(other, int):
            return NotImplemented
        elif other <= 0:
            raise ValueError('count must be positive')
        elif other == 1:
            return self
        byte_order, fmt = self._split_format
        if combine_strings:
            if fmt in ('s', 'p'):
                num_values = 1
            elif fmt == 'x':
                num_values = 0
            else:
                return NotImplemented
        else:
            num_values = self.num_values * other
        fmt = reduce(
            partial(fold_overlaps, combine_strings=combine_strings), repeat(fmt, other)
        )
        return StructSerializer(fmt, num_values, byte_order)


class StructActionSerializer(Generic[Unpack[Ts]], StructSerializer[Unpack[Ts]]):
    """A Serializer acting as a thin wrapper around struct.Struct, with
    transformations applied to unpacked values.
    """

    def __init__(
        self,
        fmt: str,
        num_attrs: int = 1,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        actions: tuple[Callable[[Any], Any], ...] = (),
    ) -> None:
        super().__init__(fmt, num_attrs, byte_order)
        self.actions = actions

    def unpack(self, buffer: ReadableBuffer) -> tuple[Unpack[Ts]]:
        return tuple(
            action(value) for action, value in zip(self.actions, super().unpack(buffer))
        )  # type: ignore

    def unpack_from(
        self, buffer: ReadableBuffer, offset: int = ...
    ) -> tuple[Unpack[Ts]]:
        return tuple(
            action(value)
            for action, value in zip(self.actions, super().unpack_from(buffer, offset))
        )  # type: ignore

    def unpack_read(self, readable: BinaryIO) -> tuple[Unpack[Ts]]:
        return tuple(
            action(value)
            for action, value in zip(self.actions, super().unpack_read(readable))
        )  # type: ignore

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        return StructActionSerializer(fmt, self.num_values, byte_order, self.actions)

    def __add__(
        self, other: StructSerializer[Unpack[Ss]]
    ) -> StructActionSerializer[Unpack[Ts], Unpack[Ss]]:
        if isinstance(other, StructActionSerializer):
            actions = other.actions
        elif isinstance(other, StructSerializer):
            actions = repeat(noop_action, other.num_values)
        else:
            return NotImplemented
        byte_order, lfmt = self._split_format
        _, rfmt = other._split_format
        fmt = fold_overlaps(lfmt, rfmt)
        num_values = self.num_values + other.num_values
        actions = tuple(chain(self.actions, actions))
        return StructActionSerializer(fmt, num_values, byte_order, actions)

    def __radd__(
        self, other: StructSerializer[Unpack[Ss]]
    ) -> StructActionSerializer[Unpack[Ss], Unpack[Ts]]:
        # NOTE: StructActionSerializer + StructActionSerializer handled by __add__
        if isinstance(other, StructSerializer):
            actions = repeat(noop_action, other.num_values)
        else:
            return NotImplemented
        byte_order, lfmt = other._split_format
        _, rfmt = self._split_format
        fmt = fold_overlaps(lfmt, rfmt)
        num_values = self.num_values + other.num_values
        actions = tuple(chain(actions, self.actions))
        return StructActionSerializer(fmt, num_values, byte_order, actions)

    def __mul__(self, other: int) -> StructActionSerializer:  # no way to hint this yet
        # TODO: Split into __mul__ and __matmul__?  Probably don't need to,
        # since __matmul__ *should* only be used for bare 's', 'p', and 'x'
        # formats, but might need to in the future if someone wants an action
        # applied to a null_char or something.
        if not isinstance(other, int):
            return NotImplemented
        elif other <= 0:
            raise ValueError('count must be positive')
        elif other == 1:
            return self
        byte_order, fmt = split_byte_order(self.format)
        fmt = reduce(fold_overlaps, [fmt] * other)
        num_values = self.num_values * other
        actions = tuple(chain.from_iterable(repeat(self.actions, other)))
        return StructActionSerializer(fmt, num_values, byte_order, actions)
