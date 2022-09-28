"""
Header serializers for Structured arrays.  We need to define these classes
explicitly so Structured can correctly gather the type hints on packed/unpacked
values.
"""
from __future__ import annotations

from functools import cache

from ..basic_types import _uint8, _uint16, _uint32, _uint64, unwrap_annotated
from ..structured import Structured
from ..type_checking import ClassVar, Generic, Optional, TypeVar, Union
from ..utils import StructuredAlias, specialized


_SizeTypes = (_uint8, _uint16, _uint32, _uint64)
SizeTypes = Union[_uint8, _uint16, _uint32, _uint64]
TSize = TypeVar('TSize', bound=SizeTypes)
TCount = TypeVar('TCount', bound=SizeTypes)


class HeaderBase:
    """Base class for all Headers.  All subclasses should expose `count` and
    `data_size` as ints, either via property or attribute.  These are not in
    the base class so as to not mess with Structured.

    TODO: Investigate if making this a Protocol will work with the desired
    effect
    """

    def __init__(self, count: int, data_size: int) -> None:
        """Set count and data_size as applicable."""

    def validate_data_size(self, data_size: int) -> None:
        """Check if `data_size`, representing the actual bytes read to unpack
        the array data, is correct.
        """


class StaticHeader(HeaderBase, Structured):
    """StaticHeader representing a statically sized array."""

    # NOTE: HeaderBase first, to get it's __init__
    _count: ClassVar[int] = 0
    data_size: ClassVar[int] = 0
    two_pass: ClassVar[bool] = False

    @property
    def count(self) -> int:
        """Expose count as a property, so we can size check on setting."""
        return self._count

    @count.setter
    def count(self, new_count: int) -> None:
        """Check for correct array length."""
        if new_count != self._count:
            raise ValueError(
                f'expected an array of length {self.count}, but got {new_count}'
            )

    @classmethod
    def specialize(cls, count: int) -> type[StaticHeader]:
        """Specialize for a specific static size."""
        if count <= 0:
            raise ValueError('count must be positive')

        class _StaticHeader(StaticHeader):
            _count: ClassVar[int] = count

        return _StaticHeader


class DynamicHeader(Generic[TCount], Structured, HeaderBase):
    """Base for dynamically sized arrays, where the array length is just prior
    to the array data.
    """

    count: TCount
    data_size: ClassVar[int] = 0
    two_pass: ClassVar[bool] = False

    def __init__(self, count: int, data_size: int) -> None:
        """Only `count` is packed/unpacked."""
        self.count = count  # type: ignore

    @classmethod
    def specialize(cls, count_type: type[SizeTypes]) -> type[DynamicHeader]:
        class _DynamicHeader(DynamicHeader[count_type]):
            pass

        return _DynamicHeader


class StaticCheckedHeader(Generic[TSize], Structured, HeaderBase):
    """Statically sized array, with a size check int packed just prior to the
    array data.
    """

    _count: ClassVar[int] = 0
    data_size: TSize
    two_pass: ClassVar[bool] = True

    def __init__(self, count: int, data_size: int) -> None:
        """Only `data_size` is packed/unpacked."""
        self.data_size = data_size  # type: ignore

    def validate_data_size(self, data_size: int) -> None:
        """Verify correct amount of bytes were read."""
        if data_size != self.data_size:
            raise ValueError(
                f'unpacking array, expected {self.data_size} bytes, but only '
                f'got {data_size}'
            )

    @property
    def count(self) -> int:
        """Count exposed as a property so we can length check on setting."""
        return self._count

    @count.setter
    def count(self, new_count: int) -> None:
        """Verify correct array length."""
        if new_count != self._count:
            raise ValueError(
                f'expected an array of length {self._count}, but got ' f'{new_count}'
            )

    @classmethod
    def specialize(
        cls,
        count: int,
        size_type: type[SizeTypes],
    ) -> type[StaticCheckedHeader]:
        """Specialize for the specific static size and check type.

        :param count: Static length for the array.
        :param size_type: Type of integer to unpack for the array data size.
        :return: The specialized Header class.
        """
        if count <= 0:
            raise ValueError('count must be positive')

        class _StaticCheckedHeader(StaticCheckedHeader[size_type]):
            _count: ClassVar[int] = count

        return _StaticCheckedHeader


class DynamicCheckedHeader(Generic[TCount, TSize], Structured, HeaderBase):
    """Dynamically sized array with a size check."""

    count: TCount
    data_size: TSize
    two_pass: ClassVar[bool] = True

    _headers = {}

    def validate_data_size(self, data_size: int) -> None:
        """Verify the correct number of bytes were read."""
        if data_size != self.data_size:
            raise ValueError(
                f'unpacking array, expected {self.data_size} bytes, but only '
                f'got {data_size}'
            )

    @classmethod
    def specialize(
        cls, count_type: type[SizeTypes], size_type: type[SizeTypes]
    ) -> type[DynamicCheckedHeader]:
        """Specialize for the specific count type and check type.

        :param count_type: Type of integer to unpack for the array length.
        :param size_type: Type of integer to unpack for the array data size.
        :return: The specialized Header class.
        """

        class _DynamicCheckedHeader(DynamicCheckedHeader[count_type, size_type]):
            pass

        return _DynamicCheckedHeader


class Header(Structured, HeaderBase):
    """Pseudo-Header class that's used to specialize to one of the concrete
    ones.
    """

    count: int
    data_size: int
    two_pass: ClassVar[bool]

    def __class_getitem__(cls, key) -> type[Header]:
        """Main entry point for making Headers.  Do type checks and create the
        appropriate Header type.
        """
        if not isinstance(key, tuple):
            key = (key,)
        return cls.create(*map(unwrap_annotated, key))

    @classmethod
    def create(cls, count, size_check=None):
        """Intermediate method to pass through default args to the real cached
        creation method.
        """
        return cls._create(count, size_check)

    @classmethod
    @cache
    def _create(
        cls, count: Union[int, type[SizeTypes]], size_check: Optional[type[SizeTypes]]
    ) -> type[Header]:
        """Check header arguments and dispatch to the correct Header
        specialization.

        :param count: Static length or integer type to unpack for array length.
        :param size_check: Integer type to unpack for array data size, or None
            for no integer to unpack.
        :return: The applicable Header specialization
        """
        # TypeVar quick out.
        if isinstance(count, TypeVar) or isinstance(size_check, TypeVar):
            return StructuredAlias(cls, (count, size_check))  # type: ignore
        # Final type checking
        if size_check is not None:
            if not (
                isinstance(size_check, type) and issubclass(size_check, _SizeTypes)
            ):
                raise TypeError('size check must be a uint* type.')
        elif not isinstance(count, int):
            if not (isinstance(count, type) and issubclass(count, _SizeTypes)):
                raise TypeError('array length must be an integer or uint* type.')
        # Dispatch
        if size_check is None:
            args = (count,)
            if isinstance(count, int):
                header = StaticHeader.specialize(count)
            else:
                header = DynamicHeader.specialize(count)
        else:
            args = (count, size_check)
            if isinstance(count, int):
                header = StaticCheckedHeader.specialize(count, size_check)
            else:
                header = DynamicCheckedHeader.specialize(count, size_check)
        return specialized(cls, *args)(header)  # type: ignore
