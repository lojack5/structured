![tests](https://github.com/lojack5/structured/actions/workflows/tests.yml/badge.svg)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

# structured - creating classes which pack and unpack with Python's `struct` module.
This is a small little library to let you leverage type hints to define classes which can also be packed and unpacked using Python's `struct` module.  The basic usage is almost like a dataclass:

```python
class MyClass(Structured):
  file_magic: char[4]
  version: uint8

a = MyClass()

with open('some_file.dat', 'rb') as ins:
  a.unpack_read(ins)
```

### Format specifiers

Almost every format specifier in `struct` is supported as a type:

| `struct` format | structured type | Python type | Notes |
|:---------------:|:---------------:|-------------|------:|
| `x`             | `pad`           |             |(1)(4) |
| `c`             | not supported   | `bytes` with length 1 | |
| `?`             | `bool8`         | `int`       |  (3)  |
| `b`             | `int8`          | `int`       |       |
| `B`             | `uint8`         | `int`       |       |
| `h`             | `int16`         | `int`       |       |
| `H`             | `uint16`        | `int`       |       |
| `i`             | `int32`         | `int`       |       |
| `I`             | `uint32`        | `int`       |       |
| `q`             | `int64`         | `int`       |       |
| `Q`             | `uint64`        | `int`       |       |
| `n`             | not supported   |             |       |
| `N`             | not supported   |             |       |
| `e`             | `float16`       | `float`     |  (2)  |
| `f`             | `float32`       | `float`     |       |
| `d`             | `float64`       | `float`     |       |
| `s`             | `char`          | `bytes`     |  (1)  |
| `p`             | `pascal`        | `bytes`     |  (1)  |
| `P`             | not supported   |             |       |

Notes:
 1. The default for this type is to unpack one of this type.  For specifying longer sequences, use indexing to specify the length.
 2. The 16-bit float type is not supported on all platforms.
 3. The `bool` type cannot be subclasses, so this is implemented as an `int`.  Packing and unpacking works that same as with `struct`.
 4. Pad variables are skipped and not actually assigned when unpacking, nor used when packing.

You can also specify byte order packing/unpacking rules, by passing a `ByteOrder` to the `Structured` metaclass on class creation.  For example:

```python
class MyClassLE(Structured, byte_order=ByteOrder.LITTLE_ENDIAN):
  magic: char[4]
  version: uint16
```

All of the specifiers are supported, the default it to use no specifier:
| `struct` specifier | `ByteOrder` |
|:------------------:|:-----------:|
| `<`                | `LITTLE_ENDIAN` (or `LE`) |
| `>`                | `BIG_ENDIAN` (or `BE`) |
| `=`                | `NATIVE_STANDARD` |
| `@`                | `NATIVE_NATIVE` |
| `!`                | `NETWORK`   |

### Using the length specified types
Pad bytes and strings often need more than one byte, use indexing to specify how many bytes they use:
```python
class MyStruct(Structured):
  magic: char[4]
  _: pad[10]
```
Now `MyStruct` has a format of `'4s10x'`.


### Creating your own types for annotations
Sometimes, the provided types are not enough.  Maybe you have a mutable type that encapsulates an integer.  To enable your type to work with `Structured` as a type annotation, you can derive from `Formatted`.  Your class will now support indexing to specify which format specifier to use to pack/unpack your class with.

```python
class MyInt(Formatted):
  _wrapped: int
  def __init__(self, value: int) -> None:
    self._wrapped = value

  def __index__(self) -> int:
    return self._wrapped

class MyStruct(Structured):
  version: MyInt[uint8]
```

The format specifier for your custom type is determined by a `__class_getitem__` method, which allows you to index the class with one of the provided format types.  By default, all of the format types are allowed.  If you want to narrow the allowed types, you can set a class variable `_types` to a set of the allowed types.  The above example is supposed to represent an integer type, so lets modify it to only allow indexing the class with integer types:

```python
class MyInt(Formatted):
  _types = {int8, int16, int32, int64, uint8, uint16, uint32, uint64}
  _wrapped: int

  def __init__(self, value: int) -> None:
    self._wrapped = value

  def __index__(self) -> int:
    return self._wrapped
```
Now trying to index with a non-integer type will raise a `TypeError`:
```python
class MyError(Structured):
  version: MyInt[float32]

>> TypeError
```

By default, a `Formatted` subclass uses the class's `__init__` to create new instances when unpacking.  If you need more flexibility, you can assign the class attribute `unpack_action` to a callable taking one argument (the result of the unpack) and returning the new instance:
```python
class MyWeirdInt(Formatted):
    def __init__(self, note: str, value: int):
      self._note = note
      self._value = value

    def __index__(self) -> int:
      return self._value

    @classmethod
    def from_unpack(cls, value: int):
      return cls('unpacked', value)

    unpack_action = from_unpack
```

As a final note, if your custom type is representing an integer, make sure to implement a `__index__` so it can be packed with `struct`.  Similarly, if it is representing a float, make sure to implement a `__float__`.

### Extending
`Structured` classes can be extended to create a new class with additional, modified, or removed attributes.  If you annotate an attribute already in the base class, it will change its format specifier to the new type.  This can be used for example, to remove an attribute from the struct packing/unpacking by annotating it with a python type rather than one of the provided types.

```python
class Base(Structured):
  a: int8
  b: int16
  c: int32

class Derived(Base):
  a: int16
  b: None
  d: float32
```
In this example, `Derived` now treats `a` as an `int16`, and ignores `b` completely when it comes to packing/unpacking.  The format string for `Derived` is now `'hif'`.

#### Extending - Byte Order
When extending a `Structured` class, the default behavior is to only allow extending if the derived class has the same byte order specifier as the base class.  If you are purposfully wanting to change the byte order, pass `byte_order_mode=ByteOrderMode.OVERRIDE` in the metaclass:
```python
class Base(Structured, byte_order=ByteOrder.LE):
  magic: char[4]
  version: uint32

class Derived(Base, byte_order=ByteOrder.BE, byte_order_mode=ByteOrderMode.OVERRIDE):
  hash: uint64
```

### Accessing `struct` details.
Any `Structured` derived class stores a class level `struct` attribute, which is an instance of `struct.Struct`.  So if you need the format string or read size, you can access these attributes:
```python
class MyStruct(Structured):
  a: int32
  b: float32

format_string = MyStruct.struct.format
format_size = MyStruct.struct.size
```

### Packing / Unpacking methods
`Structured` classes provide a couple of ways to pack and unpack their values:
 - `Structured.unpack(byteslike)`: Unpacks values from a bytes-like object and sets the instance's variables.
 - `Structured.unpack_from(buffer, offset = 0)`: Unpacks values from an object supporting the [buffer protocol](https://docs.python.org/3/c-api/buffer.html) and sets the instance's variables.
 - `Structured.unpack_read(readable)`: Reads data from a file-like object, unpacks, and sets the instance's variables.
 - `Structured.pack()`: Packs the instance's variables, returning `bytes`.
 - `Structured.pack_int(buffer, offset = 0)`: Packs the instance's variables into an object supporting the [buffer protocol](https://docs.python.org/3/c-api/buffer.html)

