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

You can also specify byte order packing/unpacking rules, by passing a `ByteOrder` to the `Structured` class on class creation.  For example:

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
When extending a `Structured` class, the default behavior is to only allow extending if the derived class has the same byte order specifier as the base class.  If you are purposfully wanting to change the byte order, pass `byte_order_mode=ByteOrderMode.OVERRIDE` in the class derivation:
```python
class Base(Structured, byte_order=ByteOrder.LE):
  magic: char[4]
  version: uint32

class Derived(Base, byte_order=ByteOrder.BE, byte_order_mode=ByteOrderMode.OVERRIDE):
  hash: uint64
```

### Accessing serialization details.
Any `Structured` derived class stores a class level `serializer` attribute, which is a `struct.Struct`-like object.  Due to the dynamic nature of some of the advanced types however, `serializer.size` is only guaranteed to be up to date with the most recent `pack_into`, `pack_write`, `unpack`, `unpack_from`, or `unpack_read`.  For `unpack` you can use `len` to get the unpacked size.  In some cases (when all class items are simple format types), `serializer` is actually a subclass of `struct.Struct`, in which case you can access all of the attributes as you would expect:
```python
class MyStruct(Structured):
  a: int32
  b: float32

assert isinstance(MyStruct.serializer, struct.Struct)
format_string = MyStruct.serializer.format
format_size = MyStruct.serializer.size
```

Also provided is `attrs`, a tuple of attribute names handled by the serializer.  You can use this for debugging purposes to verify all of the attributes you expected to be packed/unpacked are actually touched by the class.

### Packing / Unpacking methods
`Structured` classes provide a couple of ways to pack and unpack their values:
 - `Structured.unpack(byteslike)`: Unpacks values from a bytes-like object and sets the instance's variables.
 - `Structured.unpack_from(buffer, offset = 0)`: Unpacks values from an object supporting the [buffer protocol](https://docs.python.org/3/c-api/buffer.html) and sets the instance's variables.
 - `Structured.unpack_read(readable)`: Reads data from a file-like object, unpacks, and sets the instance's variables.
 - `Structured.pack()`: Packs the instance's variables, returning `bytes`.
 - `Structured.pack_int(buffer, offset = 0)`: Packs the instance's variables into an object supporting the [buffer protocol](https://docs.python.org/3/c-api/buffer.html)


## Advanced types
Structured also supports a few more complex types that require extra logic to pack and unpack.  These are:
- `char`: For unpacking binary blobs whose size is not static, but determined by data just prior to the blob (yes, it's also a basic type).
- `unicode`: For strings, automatically encoding for packing and decoding for unpacking.
- `array`: For unpacking multiple instances of a single type.  The number to unpack may be static or, like `blob`, determined by data just prior to the array.


### `char`
When `char` is used with one of `uint8`, `uint16`, `uint32` or `uint16` it becomes and advanced type.  The length of bytes to unpack is determined by the type specified.  This can be used to represent raw binary blobs of data that you do not with to decode further.  This is very similar to `pascal`, but allows for larger size indicators before the bytes.:

```python
class MyStruct(Structured):
  data: char[uint32]
```

### `unicode`
`unicode` is identical to `char` with the exception of an optional `encoding` argument, which defaults to `'utf8'`.  The size for `unicode` represents the size as bytes, not the length of the decoded string.  If you need custom encoding/decoding not provided with the built int python encodings, you can create a custom `EncoderDecoder` subclass, implementing its class methods `encode` and `decode`.

```python
class MyStruct(Structured):
  name: unicode[5]
  description: unicode[uint16]
  other: unicode[uint16, 'utf16']
```

### `array`
Arrays allow for reading in mutiple instances of one type.  These types may be any of the other basic types (except `char`, and `pascal`), or a `Structured` type.  Arrays can be used to support data that is structured in one of five ways:
- A static number of basic items packed continuously.
- A dynamic number of basic items packed continuously, preceeded by the number of items packed.
- A static number of Structured items packed continuously, preceeded by the total size of the items.
- A dynamic number of Structured items packed continuously, preceeded by the number of items packed.
- A dynamic number of Structured items packed continuously, preceeded by the number of items as well as the total size of the packed items.
To declare which type, use a specialization of the `Header` class as the first argument to your `array` specialization.  The first argument to `Header` is the array length: either an integer, or one of the `uint*` types used to unpack the length.  The second (optional) argument specifies a `uint*` type used to hold the size of the packed array items in bytes.

For example, suppose you know there will always be 10 `uint8`s in your object and you want them in an array:
```python
class MyStruct(Structured):
  items: array[Header[10], uint8]
```

Or if you need to unpack a `uint32` to determine the number of `uint8`s, then immediately unpack those items:
```python
class MyStruct(Structured):
  items: array[Header[uint32], uint8]
```

For arrays of `Structured` objects, you can optionally also provide a type to unpack, directly after the array length, which represents the packed array size in bytes.
```python
class MyItem(Structured):
  first: int8
  second: uint16

class MyStruct(Structured):
  ten_items: array[Header[10, uint32], MyItem]
  many_items: array[Header[uint32, uint32], MyItem]
```


## Notes of type checkers / IDEs
For the most part, `structured` should work with type checkers set to basic levels.  The annotated types are subclasses of their python equivalents:
- `int*` and `uint*` are subclasses of `int`.
- `float*` are subclasses of `float`.
- `bool8` is a subclass of `int`.  This is because `bool` cannot be subclassed.
- `char` and `pascal` are subclasses of `bytes`.
- `array` is a subclass of `list`.
- `unicode` is a subclass of `str`.

The trick here is that all of these types are not actually unpacked as their type.  For example an attribute marked as `array[Header[4], int8]` is unpacked as a `list[int]`.  So for the most part, type checkers will correctly identify what methods are available to each type.

The exception is assigning values to attributes, and iterating over `array`s.  For example:
```python
class MyStruct(Structured):
  a: int8

o = MyStruct(1)
o.a = 2
```
Most type checkers will warn on setting `o.a = 2`, as `int` and `int8` are incompatible here.  Similarly,
```python
class MyStruct(Structured):
  a: array[Header[2], int8]
o = MyStruct([1, 2])

o.a[1] = 2
```
Most type checkers will warn again, saying `int` is incompatible with `int8`.

One workaround is to use the `serialized` method during class creation.  This allows you to hint the type as it's actual unpacked type, but still inform the `Structured` class how to pack/unpack it:
```python
class MyStruct(Structured):
  a: int = serialized(int8)
  b: list[int] = serialized(array[Header[2], int8])
```

No solution is perfect, and any type checker set to a strict level will complain about a lot of code.


## Generic `Structured` classes
You can also create your `Structured` class as a `Generic`.  Due to details of how `typing.Generic` works, to get a working specialized version, you must subclass the specialization:

```python
class MyGeneric(Generic[T, U], Structured):
  a: T
  b: array[Header[10], U]


class ConcreteClass(MyGeneric[uint8, uint32]): pass
```
