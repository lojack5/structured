"""
Base types for all types that are handled by the Structured class.

    structured_type: The base class for every type handled by Structured.
    format_type: The base class for classes with direct correlation to static
        format strings.
    counted: A subclass of format_type that allows for specifying a count,
        specifically for 's', 'p', and 'x' format specifiers.
    Serializer: A protocol for more complex types.  To define a custom
        serializer, you should subclass from both structured_type and
        Serializer.

Serializer API:

A serializer has almost the same API as the struct.Struct class.  It must
provide the following methods and attributes:

    unpack(buffer: byteslike) -> tuple
        - Unpacks from a bytes-like buffer, returning a tuple of objects to be
          assigned to the associated attributes.
    unpack_from(buffer: BufferProtocol, offset: int = 0) -> tuple
        - Like unpack, but from an object supporting the Buffer Protocol.
    unpack_read(readable: SupportsRead) -> tuple
        - Like `unpack`, but reads in data from an objects with a `.read` method
          returning bytes.

    pack(*values) -> bytes
        - Packs the given values into bytes.
    pack_into(buffer: BufferProtocol, offset: int, *values) -> None
        - Like pack, but places the packed bytes into the Buffer Protocol
          supporting buffer, beginning at offset.
    pack_write(writable: SupportsWrite) -> None
        - Like `pack`, but writes the data into an object with a `.write` method
          taking bytes.

    size
        - A (possibly dynamic) attribute that represents the size the associated
          object's packed/unpacked data.  This attribute must be up to date with
          the most recently called of:
            - unpack
            - unpack_from
            - pack_into
          This is to support dynamically sized packing/unpacking.

    prepack(self) -> None
        - Perform any actions that need to be done prior to packing the whole
          Structured instance `obj`. This can be used, for example, to update a
          different attribute on the instance, like for an array whose size
          is stored on a seperate attribute.

Optional methods:
    TODO: Think about this one more.  It's for array's whose size is stored on
    a Structured attribute that is not directly prior to the array itself, but
    needs more thought.
    __set_name__(self, owner, name) -> None
        - Called when assigned to a Structured object, with `owner` being the
          Structured instance, and `name` being the attribute name this
          serializer will handle.  If the serializer needs more information from
          the Structured object at pack/unpack time, this is how it can be
          retrieved.
"""
from __future__ import annotations


import struct
from functools import cache, wraps
from itertools import chain
from io import BytesIO
from enum import Enum

from .utils import specialized
from .type_checking import (
    ClassVar, Callable, Any, _T, runtime_checkable, Protocol, ReadableBuffer,
    WritableBuffer, SupportsRead, SupportsWrite, Union
)


class ByteOrder(str, Enum):
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


class ByteOrderMode(str, Enum):
    """How derived classes with conflicting byte order markings should function.
    """
    OVERRIDE = 'override'
    STRICT = 'strict'


def noop_action(x: _T) -> _T:
    return x


class structured_type:
    """Base class for all types packed/unpacked by the Structured class."""


class requires_indexing(structured_type):
    """Base class for all indexed types that must be specialized before
    being used.
    """


class format_type(structured_type):
    """Base class for all types that directly correlate with a single struct
    format specifier.  The format specifier used is the class variable `format`,
    and any follow on processing can be done with the class variable
    `unpack_action`.  For packing, the applicable `__index__` or `__float__`
    method should be implemented, if not already handled by a base class.

    Types which derived from `format_type` have the advantage of being able to
    pack/unpack as one block of variables, rather than handling one at a time.
    """
    format: ClassVar[str] = ''
    unpack_action: Callable[[Any], Any] = noop_action


class counted(format_type):
    """Base class for `format_type`s that often come in continuous blocks of a
    fixed number of instances.  The examples are char and pad characters.
    """
    @classmethod
    @cache
    def __class_getitem__(cls: type[counted], count: int) -> type[counted]:
        # Error checking
        if not isinstance(count, int):
            raise TypeError('count must be an integer.')
        elif count <= 0:
            raise ValueError('count must be positive.')
        # Create the specialization
        @specialized(cls, count)
        class _counted(cls):
            format: ClassVar[str] = f'{count}{cls.format}'
        return _counted


class Serializer:
    size: int

    def pack(self, *values: Any) -> bytes:
        raise NotImplementedError
    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        raise NotImplementedError
    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        raise NotImplementedError
    def unpack(self, buffer: ReadableBuffer) -> tuple:
        raise NotImplementedError
    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        raise NotImplementedError
    def unpack_read(self, readable: SupportsRead) -> tuple:
        raise NotImplementedError

    def prepack(self, obj) -> None: pass


@runtime_checkable
class NeedsByteOrder(Protocol):
    def __init__(self, byte_order: ByteOrder) -> None: ...  # pragma: no cover


# Common implementation details for dynamically sized serializers
# Serializers in this library are implementation details, so we don't
# hide the setter behind a property
class DynamicSize:
    size: int

    def __init__(self) -> None:
        self.size = 0


# Some concrete serializers
class StructSerializer(struct.Struct, Serializer):
    def unpack_read(self, readable: SupportsRead) -> tuple:
        return self.unpack(readable.read(self.size))
    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        writable.write(self.pack(*values))


def apply_actions(unpacker):
    @wraps(unpacker)
    def wrapped(self, *args, **kwargs):
        return tuple(
            action(value)
            for action, value in zip(self.actions, unpacker(self, *args, **kwargs))
        )
    return wrapped


class StructActionSerializer(StructSerializer):
    def __init__(self, actions: tuple[Callable[[Any], Any], ...], fmt: str) -> None:
        super().__init__(fmt)
        self.actions = actions

    unpack = apply_actions(StructSerializer.unpack)
    unpack_from = apply_actions(StructSerializer.unpack_from)
    # Don't need to apply the modifier to unpack_read, as this uses the modified
    # unpack under the hood.


SerializerInfo = dict[Serializer, slice]


class CompoundSerializer(Serializer):
    """A serializer that chains together multiple serializers."""

    def __init__(self, serializers: SerializerInfo) -> None:
        self.serializers = serializers
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def prepack(self, obj) -> None:
        for serializer in self.serializers:
            serializer.prepack(obj)

    def pack(self, *values: Any) -> bytes:
        with BytesIO() as out:
            for serializer, attr_slice in self.serializers.items():
                out.write(serializer.pack(*(values[attr_slice])))
            return out.getvalue()

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        size = 0
        for serializer, attr_slice in self.serializers.items():
            serializer.pack_into(buffer, offset + size, *(values[attr_slice]))
            size += serializer.size
        self._size = size

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        for serializer, attr_slice in self.serializers.items():
            serializer.pack_write(writable, *(values[attr_slice]))

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        values = []
        start = 0
        for serializer in self.serializers:
            if isinstance(serializer, StructSerializer):
                # struct.Struct requires buffers of the exact size to unpack
                values.append(serializer.unpack(buffer[start:start + serializer.size]))
            else:
                # Custom Serializers work with buffers of unspecified length,
                # due to not necessarily knowing how must is needed to unpack
                # before hand.
                values.append(serializer.unpack(buffer[start:]))
            start += serializer.size
        self._size = start
        return tuple(chain(*values))

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        values = []
        size = 0
        for serializer in self.serializers:
            values.append(serializer.unpack_from(buffer, offset + size))
            size += serializer.size
        self._size = size
        return tuple(chain(*values))

    def unpack_read(self, readable: SupportsRead) -> tuple:
        return tuple(chain(
            *(serializer.unpack_read(readable)
              for serializer in self.serializers
             )
        ))


@cache
def struct_cache(format: str, actions: tuple[Callable[[Any], Any], ...] = ()) -> StructSerializer:
    """Cached struct.Struct creation.

    :param format: struct packing format string.
    """
    if any((action is not noop_action for action in actions)):
        return StructActionSerializer(actions, format)
    else:
        return StructSerializer(format)
