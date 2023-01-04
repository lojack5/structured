from __future__ import annotations

import sys

__all__ = [
    'Structured',
]

import operator
from functools import reduce
from itertools import count

from .base_types import ByteOrder, ByteOrderMode, requires_indexing
from .basic_types import ispad, unwrap_annotated
from .serializers import (
    AUnion,
    NullSerializer,
    Serializer,
    StructSerializer,
    StructuredSerializer,
)
from .type_checking import (
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Generic,
    Iterable,
    Iterator,
    Optional,
    ReadableBuffer,
    Self,
    TypeGuard,
    Union,
    UnionType,
    WritableBuffer,
    cast,
    get_annotations,
    get_args,
    get_origin,
    get_type_hints,
    get_union_args,
    isclassvar,
    isunion,
    update_annotations,
)
from .utils import StructuredAlias, attrgetter, zips


def validate_typehint(
    attr_type: type,
) -> TypeGuard[Union[Serializer, Structured, UnionType]]:
    """Filter to weed out only annotations which Structured uses to generate
    its serializers.  These are:
    - typing.Annotated with a Serializer as an extra argument
    - Union types

    :param attr_type: A type annotation.
    :raises TypeError: On a type that derives from `requires_indexing` but
        has not been indexed.
    """
    if isclassvar(attr_type):
        return False
    if isinstance(attr_type, type):
        if issubclass(attr_type, requires_indexing):
            raise TypeError(f'{attr_type.__qualname__} must be specialized')
        if issubclass(attr_type, Structured):
            return True
    if isinstance(attr_type, Serializer):
        return True
    if isunion(attr_type):
        return all(
            map(
                lambda x: validate_typehint(unwrap_annotated(x)),
                get_union_args(attr_type),
            )
        )
    return False


def filter_typehints(
    typehints: dict[str, Any],
) -> dict[str, Union[Serializer, Structured, UnionType]]:
    """Filters a typehints dictionary of a class for only the types which
    Structured uses to generate serializers.

    :param typehints: A class's typehints dictionary.  NOTE: This needs to be
        obtained via `get_type_hints(..., include_extras=True)`.
    :return: A filtered dictionary containing only attributes with types used
        by Structured.
    """
    return {
        attr: unwrapped
        for attr, attr_type in typehints.items()
        if validate_typehint((unwrapped := unwrap_annotated(attr_type)))
    }


def get_structured_base(cls: type[Structured]) -> Optional[type[Structured]]:
    """Given a Structured derived class, find any base classes which are also
    Structured derived.  If multiple are found, raise TypeError.

    :param cls: Structured derived class to analyze.
    :return: The direct base class which is Structured derived and not the
        Structured class itself, or None if no such base class exists.
    """
    bases = tuple(
        base
        for base in cls.__bases__
        if issubclass(base, Structured) and base is not Structured
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
    # Transform types to strings
    args_items = []
    for name, annotation in args.items():
        if union_args := get_union_args(annotation):
            union_text = ', '.join(arg.__name__ for arg in union_args)
            args_items.append(f'{name}: Union[{union_text}]')
        else:
            args_items.append(f'{name}: {annotation.__name__}')
    # Inner function text
    args_txt = ', '.join(args_items)
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


class MetaDict(dict):
    """Dictionary which assigns unique names for variables named `_` and
    annotated with `pad`.
    """

    _unique_id: ClassVar[Iterator[int]] = count()

    def __setitem__(self, key, value):
        if key == '_' and ispad(value):
            # Generate a unique name, we'll use ones that are invalid attribute
            # names so they won't accidentally overwrite anything a use sets.
            key = f'{next(self._unique_id)}_pad_'
        super().__setitem__(key, value)


class StructuredMeta(type):
    """Metaclass that simply sets the annotations dict to one that automatically
    renames `_` variables annotated with a `pad` to unique names.
    """

    def __prepare__(cls, bases, **kwargs):
        namespace = {
            '__annotations__': MetaDict(),
        }
        return namespace


class Structured(metaclass=StructuredMeta):
    """Base class for classes which can be packed/unpacked using Python's
    struct module."""

    __slots__ = ()
    serializer: ClassVar[Serializer] = StructSerializer('', 0)
    attrs: ClassVar[tuple[str, ...]] = ()
    _attrgetter: ClassVar[Callable[[Structured], tuple[Any, ...]]]
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
    def _serializer(self, packing: bool) -> Serializer:
        if packing:
            return self.serializer.prepack(self)
        else:
            return self.serializer.preunpack(self)

    def unpack(self, buffer: ReadableBuffer) -> None:
        """Unpack values from the bytes-like `buffer` and assign them to members

        :param buffer: A bytes-like object.
        """
        for attr, value in zips(
            self.attrs, self._serializer(False).unpack(buffer), strict=True
        ):
            setattr(self, attr, value)

    def unpack_read(self, readable: BinaryIO) -> None:
        """Read data from a file-like object and unpack it into values, assigned
        to this class's attributes.

        :param readable: readable file-like object.
        """
        for attr, value in zips(
            self.attrs, self._serializer(False).unpack_read(readable), strict=True
        ):
            setattr(self, attr, value)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> None:
        """Unpack values from a `buffer` implementing the buffer protocol
        starting at index `offset`, and assign them to their associated class
        members.

        :param buffer: buffer to unpack from.
        :param offset: position in the buffer to start from.
        """
        for attr, value in zips(
            self.attrs, self._serializer(False).unpack_from(buffer, offset), strict=True
        ):
            setattr(self, attr, value)

    def pack(self) -> bytes:
        """Pack the class's values according to the format string."""
        return self._serializer(True).pack(*type(self)._attrgetter(self))

    def pack_write(self, writable: BinaryIO) -> None:
        """Pack the class's values according to the format string, then write
        the result to a file-like object.

        :param writable: writable file-like object.
        """
        self._serializer(True).pack_write(writable, *type(self)._attrgetter(self))

    def pack_into(self, buffer: WritableBuffer, offset: int = 0):
        """Pack the class's values according to the format string, pkacing the
        result into `buffer` starting at position `offset`.

        :param stream: buffer to pack into.
        :param offset: position in the buffer to start writing data to.
        """
        self._serializer(True).pack_into(buffer, offset, *type(self)._attrgetter(self))

    # Creation of objects from unpackable types
    @classmethod
    def _create_proxy(cls) -> tuple[_Proxy, Serializer]:
        """Create a proxy object for this class, which can be used to create
        new instances of this class.
        """
        proxy = _Proxy(cls.attrs)
        return proxy, cls.serializer.preunpack(proxy)

    @classmethod
    def create_unpack(cls, buffer: ReadableBuffer) -> Self:
        """Create a new instance, initialized with values unpacked from a
        bytes-like buffer.

        :param buffer: A bytes-like object.
        :return: A new Structured object unpacked from the buffer.
        """
        proxy, serializer = cls._create_proxy()
        proxy(serializer.unpack(buffer))
        return cls(*proxy)

    @classmethod
    def create_unpack_from(cls, buffer: ReadableBuffer, offset: int = 0) -> Self:
        """Create a new instance, initialized with values unpacked from a buffer
        supporting the Buffer Protocol.

        :param buffer: An object supporting the Buffer Protocol.
        :param offset: Location in the buffer to begin unpacking.
        :return: A new Structured object unpacked from the buffer.
        """
        proxy, serializer = cls._create_proxy()
        proxy(serializer.unpack_from(buffer, offset))
        return cls(*proxy)

    @classmethod
    def create_unpack_read(cls, readable: BinaryIO) -> Self:
        """Create a new instance, initialized with values unpacked from a
        readable file-like object.

        :param readable: A readable file-like object.
        :return: A new Structured object unpacked from the readable object.
        """
        proxy, serializer = cls._create_proxy()
        proxy(serializer.unpack_read(readable))
        return cls(*proxy)

    def __str__(self) -> str:
        """Descriptive representation of this class."""
        vals = ', '.join((f'{attr}={getattr(self, attr)}' for attr in self.attrs))
        return f'{type(self).__name__}({vals})'

    def __repr__(self) -> str:
        return f'<{self}>'

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
        if base:
            orig_bases = getattr(cls, '__orig_bases__', ())
            base_to_origbase = {
                origin: orig_base
                for orig_base in orig_bases
                if (origin := get_origin(orig_base)) and issubclass(origin, Structured)
            }
            orig_base = base_to_origbase.get(base, None)
            if orig_base:
                annotations = base._get_specialization_hints(*get_args(orig_base))
                update_annotations(cls, annotations)
        # Analyze the class
        typehints = get_type_hints(cls, include_extras=True)
        applicable_typehints = filter_typehints(typehints)
        # Handle types that need more information from the classdict / transforming
        for attr in applicable_typehints:
            hint = applicable_typehints[attr]
            if isunion(hint):
                serializer = getattr(cls, attr, None)
                if isinstance(serializer, AUnion):
                    applicable_typehints[attr] = serializer
                else:
                    raise ValueError('Union types must be configured')
            elif isinstance(hint, type) and issubclass(hint, Structured):
                applicable_typehints[attr] = StructuredSerializer(hint)
        # All values are now Serializers
        applicable_typehints = cast(dict[str, Serializer], applicable_typehints)
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
    ) -> dict[str, Any]:
        """Get needed updates to __annotations__ and if this class were
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
        cls_annotations = get_annotations(cls)
        for attr, attr_type in get_type_hints(cls, include_extras=True).items():
            if attr in cls_annotations:
                unwrapped = unwrap_annotated(attr_type)
                # Attribute's final type hint comes from this class
                if remapped_type := tvar_map.get(unwrapped, None):
                    annotations[attr] = remapped_type
                elif isinstance(unwrapped, StructuredAlias):
                    annotations[attr] = unwrapped.resolve(tvar_map)
        # Now any classes higher in the chain
        all_annotations = [annotations]
        for base, alias in supers.items():
            args = get_args(alias)
            args = (tvar_map.get(arg, arg) for arg in args)
            super_annotations = base._get_specialization_hints(*args)
            all_annotations.append(super_annotations)
        return reduce(operator.or_, reversed(all_annotations))


class _Proxy:
    """Proxy object for a Structured instance, used as a placeholder for the
    create_unpack_*** methods to recieve values, and still allow Union deciders
    to work.
    """

    # NOTE: Only using __dunder__ methods, so any attributes on the class this
    # is a proxy for won't be shadowed.
    def __init__(self, attrs: tuple[str, ...]) -> None:
        self.__attrs = attrs

    def __call__(self, values: Iterable[Any]) -> None:
        for attr, value in zips(self.__attrs, values, strict=True):
            setattr(self, attr, value)

    def __iter__(self):
        return (getattr(self, attr) for attr in self.__attrs)
