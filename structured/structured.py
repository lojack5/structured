from __future__ import annotations

import sys

__all__ = [
    'Structured',
    'serialized',
]

import operator
from functools import cache, reduce

from .base_types import ByteOrder, ByteOrderMode, requires_indexing
from .basic_types import ispad, unwrap_annotated
from .serializers import (
    NullSerializer,
    Serializer,
    StructSerializer,
    future_requires_indexing,
)
from .type_checking import (
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Generic,
    Optional,
    ReadableBuffer,
    Self,
    TypeGuard,
    WritableBuffer,
    get_annotations,
    get_args,
    get_origin,
    get_type_hints,
    isclassvar,
    update_annotations,
)
from .utils import StructuredAlias, deprecated, warn_deprecated, attrgetter


def validate_typehint(attr_type: type) -> TypeGuard[Serializer]:
    """Filter to weed out only annotations which Structured uses to generate
    its serializers.

    :param attr_type: A type annotation.
    :raises TypeError: On a type that derives from `structured_type` but hasn't
        been implemented.  This is for devs to catch on making new types.
    """
    if isclassvar(attr_type):
        return False
    if isinstance(attr_type, type):
        if issubclass(attr_type, requires_indexing):
            raise TypeError(f'{attr_type.__qualname__} must be specialized')
        if issubclass(attr_type, (Serializer, Structured)):
            return True
        if issubclass(attr_type, future_requires_indexing):
            warn_deprecated(
                attr_type,
                '2.2',
                '3.0',
                issue=0,
                use_instead=f'Use explicit length: {attr_type.__name__}[1]',
            )
            return True
    elif isinstance(attr_type, Serializer):
        return True
    return False


@deprecated('2.1.0', '3.0', issue=5, use_instead='Annotated[unpacked_type, kind]')
def serialized(kind: Any) -> Any:
    """Type erasure for class definitions, allowing for linters to pick up the
    correct final type.  For example:

    class MyStruct(Structured):
        items: list[int] = serialized(array[4, int32])
    """
    return kind


def filter_typehints(
    typehints: dict[str, Any],
    classdict: dict[str, Any],
) -> dict[str, Serializer]:
    """Filters a typehints dictionary of a class for only the types which
    Structured uses to generate serializers.

    :param typehints: A class's typehints dictionary.  NOTE: This needs to be
        obtained via `get_type_hints(..., include_extras=True)`.
    :param classdict: The class's dictionary, used for the deprecated optional
        syntax of using `serialized`.
    :return: A filtered dictionary containing only attributes with types used
        by Structured.
    :rtype: dict[str, type[_Annotation]]
    """
    filtered = {
        attr: unwrapped
        for attr, attr_type in typehints.items()
        if validate_typehint((unwrapped := unwrap_annotated(attr_type)))
    }
    for attr, attr_type in tuple(classdict.items()):
        if validate_typehint((unwrapped := unwrap_annotated(attr_type))):
            filtered[attr] = unwrapped
            # del classdict[attr]
    # TODO: version 3.* remove this backwards compatibility for pad, char, pascal
    for attr in filtered:
        attr_type = filtered[attr]
        if isinstance(attr_type, type) and issubclass(
            attr_type, future_requires_indexing
        ):
            filtered[attr] = attr_type.serializer
    return filtered


def get_structured_base(cls: type[Structured]) -> Optional[type[Structured]]:
    """Given a Structured derived class, find any base classes which are also
    Structured derived.  If multiple are found, raise TypeError.

    :param cls: Structured derived class to analyze.
    :return: The direct base class which is Structured derived and not the
        Structured class itself, or None if no such base class exists.
    """
    bases = tuple(
        (
            base
            for base in cls.__bases__
            if issubclass(base, Structured) and base is not Structured
        )
    )
    if len(bases) > 1:
        raise TypeError(
            'Multiple inheritence from Structured base classes is not allowed.'
        )
    elif bases:
        return bases[0]
    else:
        return None


def gen_init(
    args: dict[str, Any],
    *,
    globalsns: dict[str, Any] | None = None,
    localsns: dict[str, Any] | None = None,
) -> Callable:
    """Generates an __init__ method for a class.  `args` should be a mapping of
    arguments to type annotations to be used in the method definition.

    :param args: Mapping of argument names to argument type annotations, including self.
    :param globalsns: Any globals needed to be accessed by this method.
    :param localsns: Any locals needed to be accessed by this method.
    :return: The generated __init__, without __qualname__set.
    """
    if localsns is None:
        localsns = {}
    local_vars = ', '.join(localsns.keys())
    # Inner function text
    args_txt = ', '.join(
        f'{name}: {annotation.__name__}' for name, annotation in args.items()
    )
    def_txt = f' def __init__({args_txt}) -> None:'
    body_lines = [f'  self.{name} = {name}' for name in args.keys() if name != 'self']
    body_lines.append('  self.__post_init__()')
    body_txt = '\n'.join(body_lines)
    inner_txt = f'{def_txt}\n{body_txt}'
    # Outer creation function
    txt = f'def __create_fn__({local_vars}):\n'
    txt += f'{inner_txt}\n'
    txt += ' return __init__'
    namespace = {}
    exec(txt, globalsns, namespace)
    return namespace['__create_fn__'](**localsns)


class Structured:
    """Base class for classes which can be packed/unpacked using Python's
    struct module."""

    __slots__ = ()
    serializer: ClassVar[Serializer] = StructSerializer('', 0)
    attrs: ClassVar[tuple[str, ...]] = ()
    _attrgetter: Callable[[Structured], tuple[Any, ...]]
    byte_order: ClassVar[ByteOrder] = ByteOrder.DEFAULT

    def __post_init__(self) -> None:
        """Initialize any instance variables not handled by the Structured
        unpacking logic.
        """

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        if byte_order == self.byte_order:
            return self
        serializer = self.serializer.with_byte_order(byte_order)
        new_obj = type(self)(*type(self)._attrgetter(self))
        new_obj.serializer = serializer
        new_obj.byte_order = byte_order
        return new_obj

    # General packers/unpackers
    def unpack(self, buffer: ReadableBuffer) -> None:
        """Unpack values from the bytes-like `buffer` and assign them to members

        :param buffer: A bytes-like object.
        """
        for attr, value in zip(self.attrs, self.serializer.unpack(buffer)):
            setattr(self, attr, value)

    def unpack_read(self, readable: BinaryIO) -> None:
        """Read data from a file-like object and unpack it into values, assigned
        to this class's attributes.

        :param readable: readable file-like object.
        """
        for attr, value in zip(self.attrs, self.serializer.unpack_read(readable)):
            setattr(self, attr, value)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
        """Unpack values from a `buffer` implementing the buffer protocol
        starting at index `offset`, and assign them to their associated class
        members.

        :param buffer: buffer to unpack from.
        :param offset: position in the buffer to start from.
        """
        for attr, value in zip(self.attrs, self.serializer.unpack_from(buffer, offset)):
            setattr(self, attr, value)

    def pack(self) -> bytes:
        """Pack the class's values according to the format string."""
        return self.serializer.pack(*type(self)._attrgetter(self))

    def pack_write(self, writable: BinaryIO) -> None:
        """Pack the class's values according to the format string, then write
        the result to a file-like object.

        :param writable: writable file-like object.
        """
        self.serializer.pack_write(writable, *type(self)._attrgetter(self))

    def pack_into(self, buffer: WritableBuffer, offset: int = 0):
        """Pack the class's values according to the format string, pkacing the
        result into `buffer` starting at position `offset`.

        :param stream: buffer to pack into.
        :param offset: position in the buffer to start writing data to.
        """
        self.serializer.pack_into(buffer, offset, *type(self)._attrgetter(self))

    # Creation of objects from unpackable types
    @classmethod
    def create_unpack(cls, buffer: ReadableBuffer) -> Self:
        """Create a new instance, initialized with values unpacked from a
        bytes-like buffer.

        :param buffer: A bytes-like object.
        :return: A new Structured object unpacked from the buffer.
        """
        return cls(*cls.serializer.unpack(buffer))

    @classmethod
    def create_unpack_from(cls, buffer: ReadableBuffer, offset: int = 0) -> Self:
        """Create a new instance, initialized with values unpacked from a buffer
        supporting the Buffer Protocol.

        :param buffer: An object supporting the Buffer Protocol.
        :param offset: Location in the buffer to begin unpacking.
        :return: A new Structured object unpacked from the buffer.
        """
        return cls(*cls.serializer.unpack_from(buffer, offset))

    @classmethod
    def create_unpack_read(cls, readable: BinaryIO) -> Self:
        """Create a new instance, initialized with values unpacked from a
        readable file-like object.

        :param readable: A readable file-like object.
        :return: A new Structured object unpacked from the readable object.
        """
        return cls(*cls.serializer.unpack_read(readable))

    @classmethod
    @cache
    def create_attribute_serializer(
        cls, *attributes: str
    ) -> tuple[Serializer, tuple[str, ...]]:
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
        if unhandled := attrs - set(cls.attrs):
            raise AttributeError(
                'Cannot serialize the following attributes:\n'
                f'{unhandled}\n'
                'If they are meant to be serailized, make sure to annotate '
                'them appropriately.'
            )
        # TODO: optimization possible?  Most of the calls here are cached
        # already, so the most expensive part is the get_type_hints part.  But
        # this method is cached too, so just go as is?
        items = get_type_hints(cls, include_extras=True).items()
        hints = {
            attr: unwrap_annotated(attr_type)
            for attr, attr_type in items
            if attr in attrs
        }
        serializer = sum(hints.values(), NullSerializer()).with_byte_order(
            cls.byte_order
        )
        attrs = tuple(hints.keys())
        return serializer, attrs

    def __str__(self) -> str:
        """Descriptive representation of this class."""
        vals = ', '.join((f'{attr}={getattr(self, attr)}' for attr in self.attrs))
        return f'{type(self).__name__}({vals})'

    def __eq__(self, other) -> bool:
        if type(other) == type(self):
            return all(
                (getattr(self, attr) == getattr(other, attr) for attr in self.attrs)
            )
        return NotImplemented

    def __init_subclass__(
        cls,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        byte_order_mode: ByteOrderMode = ByteOrderMode.STRICT,
        init: bool = True,
        **kwargs,
    ) -> None:
        """Subclassing a Structured type.  We need to compute new values for the
        serializer and attrs.

        :param byte_order: Which byte order to use for struct packing/unpacking.
            Defaults to no byte order marker.
        :param byte_order_mode: Mode to use when resolving conflicts with super
            class's byte order.
        :param init: Whether to generate an __init__ method for this class (for
            example, set this to false if you wish to use @dataclass).
        :raises ValueError: If ByteOrder conflicts with the base class and is
            not specified as overridden.
        """
        super().__init_subclass__(**kwargs)
        # Check for byte order conflicts
        if base := get_structured_base(cls):
            if (
                byte_order_mode is ByteOrderMode.STRICT
                and base.byte_order is not byte_order
            ):
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
                if (origin := get_origin(orig_base)) and issubclass(origin, Structured)
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
        applicable_typehints = filter_typehints(typehints, classdict)
        # Which variables show up in the __init__
        # Need to ensure 'self' shows up first
        typehints = get_type_hints(cls)
        init_vars = {'self': Self}
        init_vars |= {
            attr: typehints.get(attr, Any)
            for attr in applicable_typehints
            if not ispad(applicable_typehints[attr])
        }
        # But also don't want 'self' to show up in attrs
        attrs = tuple(init_vars.keys())[1:]
        serializer = sum(
            applicable_typehints.values(), NullSerializer()
        ).with_byte_order(byte_order)
        if init:
            # Generate an init method
            if cls.__module__ in sys.modules:
                globals = sys.modules[cls.__module__].__dict__
            else:
                globals = {}

            init_fn = gen_init(init_vars, globalsns=globals)
            init_fn.__qualname__ = f'{cls.__qualname__}.__init__'
            cls.__init__ = init_fn
        # And set the updated class attributes
        cls.serializer = serializer
        cls.attrs = attrs
        cls._attrgetter = attrgetter(*attrs)
        cls.byte_order = byte_order

    @classmethod
    def _get_specialization_hints(
        cls,
        *args,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Get needed updates to __annotations__ and __dict__ if this class were
        to be specialized with `args`,
        """
        supers: dict[type[Structured], Any] = {}
        tvars = ()
        for base in getattr(cls, '__orig_bases__', ()):
            if (origin := get_origin(base)) is Generic:
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
                unwrapped = unwrap_annotated(attr_type)
                # Attribute's final type hint comes from this class
                if remapped_type := tvar_map.get(unwrapped, None):
                    annotations[attr] = remapped_type
                elif isinstance(unwrapped, StructuredAlias):
                    annotations[attr] = unwrapped.resolve(tvar_map)
        for attr, attr_val in cls.__dict__.items():
            unwrapped = unwrap_annotated(attr_val)
            if isinstance(unwrapped, StructuredAlias):
                classdict[attr] = unwrapped.resolve(tvar_map)
        # Now any classes higher in the chain
        all_annotations = [annotations]
        all_classdict = [classdict]
        for base, alias in supers.items():
            args = get_args(alias)
            args = (tvar_map.get(arg, arg) for arg in args)
            super_annotations, super_classdict = base._get_specialization_hints(*args)
            all_annotations.append(super_annotations)
            all_classdict.append(super_classdict)
        final_annotations = reduce(operator.or_, reversed(all_annotations))
        final_classdict = reduce(operator.or_, reversed(all_classdict))
        return final_annotations, final_classdict
