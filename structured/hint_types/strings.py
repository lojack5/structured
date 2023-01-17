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
from ..utils import StructuredAlias, HintType, ArgType
from .basic_types import _SizeTypes, _TSize


class NET:
    """Marker class for denoting .NET strings."""


class Count(ArgType):
    """Helper class for denoting the count argument for char and unicode.

    Usage:
        char[Count[3]]
        char[Count[uint32]]
        char[Count[NET]]
        char[Count[b'\x00']]
    """
    name = 'count'


class char(bytes, requires_indexing, HintType):
    """A bytestring, with three ways of denoting length. If size is an integer,
    it is a static size.  If a uint* type is specified, it is prefixed with
    a packed value of that type which holds the length.  If the NET type is
    specified, uses the variable (1-2 bytes) .NET string size marker.  If a
    single byte is specified, it's is interpreted as a terminator byte.

        char[3] - statically sized.
        char[uint32] - dynamically sized.
        char[NET] - dynamically sized.
        char[b'\x00'] - terminated with a NULL byte.

    :param size: The size of the bytestring.
    :type size: Union[int, bytes
                      type[Union[uint8, uint16, uint32, uint64]],
                      type[NET]]
    """
    @classmethod
    @cache
    def create(cls, count: Union[int, type[_TSize], type[NET], bytes]) -> TCharSerializer:
        if count in _SizeTypes:
            unwrapped = annotated(StructSerializer[int]).extract(count)
            if unwrapped:  # Always True for _SizeTypes
                serializer = DynamicCharSerializer(unwrapped)
            else:
                raise RuntimeError('Internal error')
        elif isinstance(count, int):
            serializer = static_char_serializer(count)
        elif count is NET:
            serializer = NETCharSerializer()
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


class Encoding(ArgType):
    name = 'encoding'


class unicode(str, requires_indexing, HintType):
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
        serializer = annotated(Serializer).extract(char[count])
        serializer = cast(TCharSerializer, serializer)  # definitely is at this point
        return Annotated[
            str, UnicodeSerializer(serializer, encoder, decoder)
        ]  # type: ignore


null_char = char[b'\0']
null_unicode = unicode[b'\0']
