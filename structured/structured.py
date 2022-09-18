from __future__ import annotations
import operator
from typing import get_args, get_origin
import typing

from structured.utils import StructuredAlias

__all__ = [
    'Structured',
    'ByteOrder', 'ByteOrderMode',
    'serialized',
    'create_serializer',
]

from functools import reduce
import re

from .base_types import *
from .basic_types import pad, unwrap_annotated
from .utils import deprecated
from .type_checking import (
    Any, ClassVar, Optional, ReadableBuffer, SupportsRead, SupportsWrite,
    WritableBuffer, get_type_hints, isclassvar, cast, TypeGuard, Union, TypeVar,
    get_annotations, update_annotations,
)


_Annotation = Union[format_type, Serializer]

def validate_typehint(attr_type: type) -> TypeGuard[type[_Annotation]]:
    if isclassvar(attr_type):
        return False
    if isinstance(attr_type, type):
        if issubclass(attr_type, requires_indexing):
            raise TypeError(f'{attr_type.__qualname__} must be specialized')
        if issubclass(attr_type, structured_type):
            if issubclass(attr_type, (format_type, Serializer)):
                return True
            else:
                raise TypeError(
                    f'Unknown structured type {attr_type.__qualname__}'
                )
    return False


@deprecated('2.1.0', issue=5, use_instead='Annotated[unpacked_type, kind]')
def serialized(kind: type[structured_type]) -> Any:
    """Type erasure for class definitions, allowing for linters to pick up the
    correct final type.  For example:

    class MyStruct(Structured):
        items: list[int] = serialized(array[4, int32])
    """
    return kind


def filter_typehints(
        typehints: dict[str, Any],
        classdict: dict[str, Any],
    ) -> dict[str, type[_Annotation]]:
    filtered = {
        attr: unwrapped
        for attr, attr_type in typehints.items()
        if validate_typehint((unwrapped := unwrap_annotated(attr_type)))
    }
    for attr, attr_type in tuple(classdict.items()):
        if validate_typehint((unwrapped := unwrap_annotated(attr_type))):
            filtered[attr] = unwrapped
            #del classdict[attr]
    return filtered


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
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        classdict: Optional[dict[str, Any]] = None,
    ) -> tuple[Serializer, tuple[str, ...]]:
    """Create a Serializer appropriate for packing/unpacking attributes.
    Attributes are matched first by searching through `typhints` for names with
    applicable Structured types.  Optionally (used internally for class
    creation), a class dictionary can be passed as well, overriding hints from
    the typhints dictionary.

    :param typehints: Mapping of attribute names to types.
    :param byte_order: Byte order to be used when unpacking/packing.
    :param classdict: Optional second mapping of attribute names to types.
    :return: A Serializer instance to use for packing/unpacking the matching
        attributes, along with said attributes in the order they will be
        serialized.
    """
    classdict = classdict if classdict is not None else {}
    applicable_hints = filter_typehints(typehints, classdict)
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


def get_structured_base(cls: type[Structured]) -> Optional[type[Structured]]:
    """Given a Structured derived class, find any base classes which are also
    Structured derived.  If multiple are found, raise TypeError.

    :param cls: Structured derived class to analyze.
    :return: The direct base class which is Structured derived and not the
        Structured class itself, or None if no such base class exists.
    """
    bases = tuple((
        base for base in cls.__bases__
        if issubclass(base, Structured) and base is not Structured
    ))
    if len(bases) > 1:
        raise TypeError(
            'Multiple inheritence from Structured base classes is not allowed.'
        )
    elif bases:
        return bases[0]
    else:
        return None


_C = TypeVar('_C', bound='Structured')
class Structured:
    """Base class for classes which can be packed/unpacked using Python's
    struct module."""
    __slots__ = ()
    serializer: ClassVar[Serializer] = struct_cache('')
    attrs: ClassVar[tuple[str, ...]] = ()
    byte_order: ClassVar[ByteOrder] = ByteOrder.DEFAULT

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

    ## General packers/unpackers
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

    ## Creation of objects from unpackable types
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

    @classmethod
    @cache
    def create_attribute_serializer(cls, *attributes: str) -> tuple[Serializer, tuple[str, ...]]:
        """Create a serializer for handling just the given attributes.  This may
        be as simple as returning the default serializer, or returning a sub
        serializer in a CompoundSerializer.  Otherwise, a new one will have to
        be created.

        :return: A serializer suitable for packing/unpacking the given
            attributes.
        """
        attrs = set(attributes)
        num_requested = len(attrs)
        num_attrs = len(cls.attrs)
        if num_requested < num_attrs:
            # TODO: Say which ones
            raise AttributeError('Attributes specified multiple times.')
        if (unhandled := attrs - set(cls.attrs)):
            raise AttributeError(
                 'Cannot serialize the following attributes:\n'
                f'{unhandled}\n'
                 'If they are meant to be serailized, make sure to annotate '
                 'them appropriately.'
                )
        # TODO: optimization possible?  Most of the calls here are cached
        # already, so the most expensive part is the get_type_hints part.  But
        # this method is cached too, so just go as is?
        hints = {
            attr: attr_type
            for attr, attr_type in get_type_hints(cls, include_extras=True).items()
            if attr in attrs
        }
        return create_serializer(hints, cls.byte_order)


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

    def __init_subclass__(
            cls,
            byte_order: ByteOrder = ByteOrder.DEFAULT,
            byte_order_mode: ByteOrderMode = ByteOrderMode.STRICT,
            **kwargs,
        ) -> None:
        """Subclassing a Structured type.  We need to compute new values for the
        serializer and attrs.

        :param byte_order: Which byte order to use for struct packing/unpacking.
            Defaults to no byte order marker.
        :param byte_order_mode: Mode to use when resolving conflicts with super
            class's byte order.
        :raises ValueError: _description_
        """
        super().__init_subclass__(**kwargs)
        # Check for byte order conflicts
        if (base := get_structured_base(cls)):
            if (byte_order_mode is ByteOrderMode.STRICT and
                base.byte_order is not byte_order):
                raise ValueError(
                    'Incompatable byte order specifications between class '
                    f'{cls.__name__} ({byte_order.name}) and base class '
                    f'{base.__name__} ({base.byte_order.name}). '
                    'If this is intentional, use `byte_order_mode=OVERRIDE`.'
                )
        # Evaluta any generics in base class
        classdict = cls.__dict__
        if base:
            orig_bases = getattr(cls, '__orig_bases__', ())
            base_to_origbase = {
                origin: orig_base
                for orig_base in orig_bases
                if (origin := get_origin(orig_base))
                    and issubclass(origin, Structured)
            }
            orig_base = base_to_origbase.get(base, None)
            if orig_base:
                annotations, clsdict = base._get_specialization_hints(
                    *get_args(orig_base)
                )
                update_annotations(cls, annotations)
                # NOTE: cls.__dict__ is a mappingproxy
                classdict = dict(classdict) | clsdict
        # Analyze the class
        typehints = get_type_hints(cls, include_extras=True)
        serializer, attrs = create_serializer(typehints, byte_order, classdict)
        # And set the updated class attributes
        cls.serializer = serializer
        cls.attrs = attrs
        cls.byte_order = byte_order



    @classmethod
    def _get_specialization_hints(
            cls,
            *args
        ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Get needed updates to __annotations__ and __dict if this class were
        to be specialized with `args`,
        """
        supers: dict[type[Structured], Any] = {}
        tvars = ()
        for base in getattr(cls, '__orig_bases__', ()):
            if (origin := get_origin(base)) is typing.Generic:
                tvars = get_args(base)
            elif origin and issubclass(origin, Structured):
                supers[origin] = base
        tvar_map = dict(zip(tvars, args))
        if not tvar_map:
            raise TypeError(f'{cls.__name__} is not a Generic')
        # First handle the direct base class
        annotations = {}
        classdict = {}
        cls_annotations = get_annotations(cls)
        for attr, attr_type in get_type_hints(cls, include_extras=True).items():
            if attr in cls_annotations:
                # Attribute's final type hint comes from this class
                if remapped_type := tvar_map.get(attr_type, None):
                    annotations[attr] = remapped_type
                elif isinstance(attr_type, StructuredAlias):
                    annotations[attr] = attr_type.resolve(tvar_map)
        for attr, attr_val in cls.__dict__.items():
            if isinstance(attr_val, StructuredAlias):
                classdict[attr] = attr_val.resolve(tvar_map)
        # Now any classes higher in the chain
        all_annotations = [annotations]
        all_classdict = [classdict]
        for base, alias in supers.items():
            args = get_args(alias)
            args = (tvar_map.get(arg, arg) for arg in args)
            super_annotations, super_classdict = base._get_specialization_hints(
                *args
            )
            all_annotations.append(super_annotations)
            all_classdict.append(super_classdict)
        final_annotations = reduce(operator.or_, reversed(all_annotations))
        final_classdict = reduce(operator.or_, reversed(all_classdict))
        return final_annotations, final_classdict
