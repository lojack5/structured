"""
Basic buliding block serializer for most other serializers.  Just thin wrappers
around struct.Struct.
"""

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
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Callable,
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


def compute_num_values(st: struct.Struct, *, __cache: dict[str, int] = {}) -> int:
    """Determine how many values are used in packing/unpacking a struct format."""
    try:
        return __cache[st.format]
    except KeyError:
        buffer = bytearray(st.size)
        # Use struct.Struct so this can be called before full initialization of
        # subclasses.
        count = len(struct.Struct.unpack_from(st, buffer))
        __cache[st.format] = count
        return count


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
        byte_order: ByteOrder = ByteOrder.DEFAULT,
    ) -> None:
        super().__init__(byte_order.value + format)
        self.num_values = compute_num_values(self)

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.format}, {self.num_values})'

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        else:
            return type(self)(fmt, byte_order)

    def unpack(self, buffer: ReadableBuffer) -> tuple[Unpack[Ts]]:
        return super().unpack(buffer[: self.size])  # type: ignore

    if TYPE_CHECKING:

        def unpack_from(
            self, buffer: ReadableBuffer, offset: int = 0
        ) -> tuple[Unpack[Ts]]: ...

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
    ) -> StructSerializer[Unpack[Ts], Unpack[Ss]]: ...

    @overload
    def __add__(
        self, other: Serializer[Unpack[Ss]]
    ) -> Serializer[Unpack[Ts], Unpack[Ss]]: ...

    def __add__(self, other: Serializer) -> Serializer:
        if isinstance(other, StructSerializer):
            # Don't need a CompoundSerializer for joining with another Struct
            byte_order, lfmt = self._split_format
            byte_order2, rfmt = other._split_format
            if byte_order is not byte_order2:
                raise ValueError(
                    f'Cannot join StructSerializers with different byte orders: '
                    f'{self} + {other}'
                )
            return type(self)(
                fold_overlaps(lfmt, rfmt),
                byte_order,
            )
        return super().__add__(other)

    def __mul__(self, other: int) -> Self:  # no tool to hint the [] yet
        """Return a new StructSerializer that unpacks `other` copies of the
        kine this one does.  I.e: for non-string types it puts a multiplier
        number in front of the format specifier, for strings it repeats the
        format specifier.
        """
        return self._mul_impl(other)

    def __matmul__(self, other: int) -> Self:
        """Return a new StructSerializer that folds strings together when
        multiplying.  NOTE: This is only supported for StructSerializers that
        consist of either a 's', 'p', or 'x' format specifier.
        """
        return self._mul_impl(other, True)

    def _mul_impl(self, other: int, combine_strings: bool = False) -> Self:
        if not isinstance(other, int):
            return NotImplemented
        elif other <= 0:
            raise ValueError('count must be positive')
        elif other == 1:
            return self
        byte_order, fmt = self._split_format
        fmt = reduce(
            partial(fold_overlaps, combine_strings=combine_strings), repeat(fmt, other)
        )
        return type(self)(fmt, byte_order)

    def __eq__(self, other: StructSerializer) -> bool:
        if isinstance(other, StructSerializer):
            return self.format == other.format and self.num_values == other.num_values
        else:
            return NotImplemented

    def __hash__(self) -> int:
        return hash((self.format, self.num_values))


class StructActionSerializer(Generic[Unpack[Ts]], StructSerializer[Unpack[Ts]]):
    """A Serializer acting as a thin wrapper around struct.Struct, with
    transformations applied to unpacked values.
    """

    actions: tuple[Callable[[Any], Any], ...]

    def __new__(
        cls,
        fmt: str,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        actions: tuple[Callable[[Any], Any], ...] = (),
    ) -> Self:
        return super().__new__(cls, fmt, byte_order)

    def __init__(
        self,
        fmt: str,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        actions: tuple[Callable[[Any], Any], ...] = (),
    ) -> None:
        super().__init__(fmt, byte_order)
        if len(actions) < self.num_values:
            actions = tuple(
                chain(actions, repeat(noop_action, self.num_values - len(actions)))
            )
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
        res = super().with_byte_order(byte_order)
        if res is not self:
            res.actions = self.actions
        return res

    @overload
    def __add__(
        self, other: StructSerializer[Unpack[Ss]]
    ) -> StructActionSerializer[Unpack[Ts], Unpack[Ss]]: ...

    @overload
    def __add__(
        self, other: Serializer[Unpack[Ss]]
    ) -> Serializer[Unpack[Ts], Unpack[Ss]]: ...

    def __add__(self, other: Serializer) -> Serializer:
        if isinstance(other, StructActionSerializer):
            actions = other.actions
        elif isinstance(other, StructSerializer):
            actions = ()
        else:
            return super().__add__(other)
        byte_order, lfmt = self._split_format
        _, rfmt = other._split_format
        fmt = fold_overlaps(lfmt, rfmt)
        actions = tuple(chain(self.actions, actions))
        return type(self)(fmt, byte_order, actions)

    def __radd__(
        self, other: StructSerializer[Unpack[Ss]]
    ) -> StructActionSerializer[Unpack[Ss], Unpack[Ts]]:
        if isinstance(other, StructSerializer):
            actions = repeat(noop_action, other.num_values)
        else:
            return NotImplemented
        byte_order, lfmt = other._split_format
        _, rfmt = self._split_format
        fmt = fold_overlaps(lfmt, rfmt)
        actions = tuple(chain(actions, self.actions))
        return type(self)(fmt, byte_order, actions)  # type: ignore

    def __mul__(self, other: int) -> StructActionSerializer:  # no way to hint this yet
        res = super().__mul__(other)
        res.actions = tuple(chain.from_iterable(repeat(self.actions, other)))
        return res

    def __eq__(self, other: StructSerializer) -> bool:
        if isinstance(other, StructActionSerializer):
            return self.format == other.format and self.actions == other.actions
        elif isinstance(other, StructSerializer):
            return False
        else:
            return NotImplemented

    def __hash__(self) -> int:
        return hash((self.format, self.num_values, self.actions))
