"""
Char and Unicode typhint classes, which dispatch to the appropriate serializer
based on provided specialization args.
"""

__all__ = [
    'EncoderDecoder',
    'unicode',
    'char',
    'null_unicode',
    'null_char',
    'NET',
]

from functools import cache, partial

from ..base_types import requires_indexing
from ..serializers import (
    DynamicCharSerializer,
    NETCharSerializer,
    Serializer,
    StructSerializer,
    TCharSerializer,
    TerminatedCharSerializer,
    UnicodeSerializer,
    static_char_serializer,
)
from ..type_checking import Annotated, TypeVar, Union, annotated, cast
from ..utils import StructuredAlias
from .basic_types import _SizeTypes, _TSize


class NET:
    """Marker class for denoting .NET strings."""


class char(bytes, requires_indexing):
    """A bytestring, with three ways of denoting length. If size is an integer,
    it is a static size.  If a uint* type is specified, it is prefixed with
    a packed value of that type which holds the length.  If the NET type is
    specified, uses the variable (1-2 bytes) .NET string size marker.

        char[3] - statically sized.
        char[uint32] - dynamically sized.
        char[NET] - dynamically sized.

    :param size: The size of the bytestring.
    :type size: Union[int,
                      type[Union[uint8, uint16, uint32, uint64]],
                      type[NET]]
    """

    def __class_getitem__(cls, args) -> TCharSerializer:
        """Create a char specialization."""
        if not isinstance(args, tuple):
            args = (args,)
        return cls._create(*args)

    @classmethod
    @cache
    def _create(
        cls,
        count: Union[int, type[_TSize], type[NET]],
    ) -> TCharSerializer:
        if count in _SizeTypes:
            count = annotated.transform(count)
            serializer = DynamicCharSerializer(count)
        elif isinstance(count, int):
            serializer = static_char_serializer(count)
        elif count is NET:
            serializer = NETCharSerializer()
        elif isinstance(count, TypeVar):
            return StructuredAlias(cls, (count,))  # type: ignore
        elif isinstance(count, bytes):
            serializer = TerminatedCharSerializer(count)
        else:
            raise TypeError(
                f'{cls.__qualname__}[] count must be an int, NET, terminator '
                f'byte, or uint* type, got {count!r}'
            )
        return Annotated[bytes, serializer]  # type: ignore


class EncoderDecoder:
    """Base class for creating custom encoding/decoding methods for strings.
    Subclass and implement encode for encoding a string to bytes, and decode
    for decoding a string from bytes.
    """

    @classmethod
    def encode(cls, strng: str) -> bytes:
        """Encode `strng`.

        :param strng: String to encode.
        :return: The encoded bytestring.
        """
        raise NotImplementedError

    @classmethod
    def decode(cls, byts: bytes) -> str:
        """Decode `byts`.

        :param byts: The bytestring to decode.
        :return: The decoded string.
        :rtype: str
        """
        raise NotImplementedError


class unicode(str, requires_indexing):
    """A char-like type which is automatically encoded when packing and decoded
    when unpacking.  Arguments are the same as for char, with an additional
    optional argument `encoding`.  If encoding is a string, it is the name of
    a python standard codec to use.  Otherwise, it must be a subclass of
    `EncoderDecoder` to provide the encoding and decoding methods.

    :param size: The size of the *encoded* string.
    :type size: Union[int,
                      Union[type[uint8, uint16, uint32, uint64]],
                      type[NET]]
    :param encoding: Encoding method to use.
    :type encoding: Union[str, type[EncoderDecoder]]
    """

    @classmethod
    def __class_getitem__(cls, args) -> Serializer[str]:
        """Create the specialization."""
        if not isinstance(args, tuple):
            args = (args,)
        return cls.create(*args)

    @classmethod
    def create(
        cls,
        count: Union[int, type[_TSize], type[NET]],
        encoding: Union[str, type[EncoderDecoder]] = 'utf8',
    ) -> Serializer[str]:
        # Double indirection so @cache can see the default args
        # as actual args.
        return cls._create(count, encoding)

    @classmethod
    @cache
    def _create(
        cls,
        count: Union[int, type[_TSize], type[NET]],
        encoding: Union[str, type[EncoderDecoder]],
    ) -> Serializer[str]:
        """Create the specialization.

        :param count: Size of the *encoded* string.
        :param encoding: Encoding method to use.
        :return: The specialized class.
        """
        # Encoding/Decoding method
        if isinstance(count, TypeVar):
            return StructuredAlias(cls, (count, encoding))  # type: ignore
        if isinstance(encoding, str):
            encoder = partial(str.encode, encoding=encoding)
            decoder = partial(bytes.decode, encoding=encoding)
        elif (
            isinstance(encoding, type)
            and issubclass(encoding, EncoderDecoder)
            or isinstance(encoding, EncoderDecoder)
        ):
            encoder = encoding.encode
            decoder = encoding.decode
        else:
            raise TypeError('An encoding or an EncoderDecoder must be specified.')
        serializer = annotated.transform(char[count])
        serializer = cast(TCharSerializer, serializer)  # definitely is at this point
        return Annotated[
            str, UnicodeSerializer(serializer, encoder, decoder)
        ]  # type: ignore


null_char = char[b'\0']
null_unicode = unicode[b'\0']
