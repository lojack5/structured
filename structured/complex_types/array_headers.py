"""
Header serializers for Structured arrays.  We need to define these classes
explicitly so Structured can correctly gather the type hints on packed/unpacked
values.
"""
from __future__ import annotations

from functools import cache

from ..utils import specialized
from ..structured import Structured
from ..basic_types import uint8, uint16, uint32, uint64
from ..type_checking import ClassVar, Union


SizeTypes = Union[uint8, uint16, uint32, uint64]


class HeaderBase:
    def __init__(self, count: int, data_size: int) -> None:
        pass

    def validate_data_size(self, data_size: int) -> None:
        pass


class StaticHeader(HeaderBase, Structured):
    # NOTE: HeaderBase first, to get it's __init__
    _count: ClassVar[int] = 0
    data_size: ClassVar[int] = 0
    two_pass: ClassVar[bool] = False

    @property
    def count(self) -> int:
        return self._count
    @count.setter
    def count(self, new_count: int) -> None:
        if new_count != self._count:
            raise ValueError(f'expected an array of length {self.count}, but got {new_count}')

    def __class_getitem__(cls: type[StaticHeader], count: int) -> type[StaticHeader]:
        if count <= 0:
            raise ValueError('count must be positive')
        class _StaticHeader(cls):
            _count: ClassVar[int] = count
        return _StaticHeader


class DynamicHeader(Structured, HeaderBase):
    count: int
    data_size: ClassVar[int] = 0
    two_pass: ClassVar[bool] = False

    _headers = {}

    def __init__(self, count: int, data_size: int) -> None:
        self.count = count

    def validate_data_size(self, data_size: int) -> None:
        pass

    def __class_getitem__(cls, count_type: type[SizeTypes]) -> type[DynamicHeader]:
        return cls._headers[count_type]
class _DynamicHeader8(DynamicHeader):
    count: uint8
class _DynamicHeader16(DynamicHeader):
    count: uint16
class _DynamicHeader32(DynamicHeader):
    count: uint32
class _DynamicHeader64(DynamicHeader):
    count: uint64
DynamicHeader._headers = {
    uint8: _DynamicHeader8,
    uint16: _DynamicHeader16,
    uint32: _DynamicHeader32,
    uint64: _DynamicHeader64,
}


class StaticCheckedHeader(Structured, HeaderBase):
    _count: ClassVar[int] = 0
    data_size: int
    two_pass: ClassVar[bool] = True

    _headers = {}

    def __init__(self, count: int, data_size: int) -> None:
        self.data_size = data_size

    def validate_data_size(self, data_size: int) -> None:
        if data_size != self.data_size:
            raise ValueError(f'unpacking array, expected {self.data_size} bytes, but only got {data_size}')

    @property
    def count(self) -> int:
        return self._count
    @count.setter
    def count(self, new_count: int) -> None:
        if new_count != self._count:
            raise ValueError(f'expected an array of length {self._count}, but got {new_count}')

    def __class_getitem__(cls: type[StaticCheckedHeader], key: tuple[int, type[SizeTypes]]) -> type[StaticCheckedHeader]:
        count, size_type = key
        if count <= 0:
            raise ValueError('count must be positive')
        base = cls._headers[size_type]
        class _StaticCheckedHeader(base):
            _count: ClassVar[int] = count
        return _StaticCheckedHeader
class _StaticCheckedHeader8(StaticCheckedHeader):
    data_size: uint8
class _StaticCheckedHeader16(StaticCheckedHeader):
    data_size: uint16
class _StaticChechedHeader32(StaticCheckedHeader):
    data_size: uint32
class _StaticCheckedHeader64(StaticCheckedHeader):
    data_size: uint64
StaticCheckedHeader._headers = {
    uint8: _StaticCheckedHeader8,
    uint16: _StaticCheckedHeader16,
    uint32: _StaticChechedHeader32,
    uint64: _StaticCheckedHeader64,
}


class DynamicCheckedHeader(Structured, HeaderBase):
    count: int
    data_size: int
    two_pass: ClassVar[bool] = True

    _headers = {}

    def validate_data_size(self, data_size: int) -> None:
        if data_size != self.data_size:
            raise ValueError(f'unpacking array, expected {self.data_size} bytes, but only got {data_size}')

    def __class_getitem__(cls: type[DynamicCheckedHeader], key: tuple[type[SizeTypes], type[SizeTypes]]) -> type[DynamicCheckedHeader]:
        return cls._headers[key]
class _DynamicCheckedHeader8_8(DynamicCheckedHeader):
    count: uint8
    data_size: uint8
class _DynamicCheckedHeader8_16(DynamicCheckedHeader):
    count: uint8
    data_size: uint16
class _DynamicCheckedHeader8_32(DynamicCheckedHeader):
    count: uint8
    data_size: uint32
class _DynamicCheckedHeader8_64(DynamicCheckedHeader):
    count: uint8
    data_size: uint64
class _DynamicCheckedHeader16_8(DynamicCheckedHeader):
    count: uint16
    data_size: uint8
class _DynamicCheckedHeader16_16(DynamicCheckedHeader):
    count: uint16
    data_size: uint16
class _DynamicCheckedHeader16_32(DynamicCheckedHeader):
    count: uint16
    data_size: uint32
class _DynamicCheckedHeader16_64(DynamicCheckedHeader):
    count: uint16
    data_size: uint64
class _DynamicCheckedHeader32_8(DynamicCheckedHeader):
    count: uint32
    data_size: uint8
class _DynamicCheckedHeader32_16(DynamicCheckedHeader):
    count: uint32
    data_size: uint16
class _DynamicCheckedHeader32_32(DynamicCheckedHeader):
    count: uint32
    data_size: uint32
class _DynamicCheckedHeader32_64(DynamicCheckedHeader):
    count: uint32
    data_size: uint64
class _DynamicCheckedHeader64_8(DynamicCheckedHeader):
    count: uint64
    data_size: uint8
class _DynamicCheckedHeader64_16(DynamicCheckedHeader):
    count: uint64
    data_size: uint16
class _DynamicCheckedHeader64_32(DynamicCheckedHeader):
    count: uint64
    data_size: uint32
class _DynamicCheckedHeader64_64(DynamicCheckedHeader):
    count: uint64
    data_size: uint64
DynamicCheckedHeader._headers = {
    (uint8, uint8): _DynamicCheckedHeader8_8,
    (uint8, uint16): _DynamicCheckedHeader8_16,
    (uint8, uint32): _DynamicCheckedHeader8_32,
    (uint8, uint64): _DynamicCheckedHeader8_64,
    (uint16, uint8): _DynamicCheckedHeader16_8,
    (uint16, uint16): _DynamicCheckedHeader16_16,
    (uint16, uint32): _DynamicCheckedHeader16_32,
    (uint16, uint64): _DynamicCheckedHeader16_64,
    (uint32, uint8): _DynamicCheckedHeader32_8,
    (uint32, uint16): _DynamicCheckedHeader32_16,
    (uint32, uint32): _DynamicCheckedHeader32_32,
    (uint32, uint64): _DynamicCheckedHeader32_64,
    (uint64, uint8): _DynamicCheckedHeader64_8,
    (uint64, uint16): _DynamicCheckedHeader64_16,
    (uint64, uint32): _DynamicCheckedHeader64_32,
    (uint64, uint64): _DynamicCheckedHeader64_64,
}


class Header(Structured, HeaderBase):
    """Pseudo-Header class that's used to specialize to one of the concrete ones."""
    count: int
    data_size: int
    two_pass: ClassVar[bool]

    @classmethod
    @cache
    def __class_getitem__(cls, key) -> type[Header]:
        if not isinstance(key, tuple):
            count, size_check = key, None
        elif len(key) != 2:
            raise TypeError(f'{cls.__name__}[] expected two arguments')
        else:
            count, size_check = key
        try:
            if size_check is None:
                args = (count,)
                if isinstance(count, int):
                    header = StaticHeader[count]
                else:
                    header = DynamicHeader[count]
            else:
                args = (count, size_check)
                if isinstance(count, int):
                    header = StaticCheckedHeader[count, size_check]
                else:
                    header = DynamicCheckedHeader[count, size_check]
            return specialized(cls, *args)(header)  # type: ignore
        except KeyError:
            raise TypeError(f'{cls.__name__}[] expected first argument integer or uint* type, second argument uint* type or None') from None
