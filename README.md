![tests](https://github.com/lojack5/structured/actions/workflows/tests.yml/badge.svg)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

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

### Format specifiers (basic types)

Almost every format specifier in `struct` is supported as a type:

| `struct` format | structured type | Python type | Notes |
|:---------------:|:---------------:|-------------|:-----:|
| `x`             | `pad`           |             |(1)(4) |
| `c`             | `char`          | `bytes` with length 1 | |
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
 1. The default for this a single instance of this type.  For specifying longer sequences, use indexing to specify the length.
 2. The 16-bit float type is not supported on all platforms.
 3. `struct` treats `bool` as an `int`, so this is implemented as an `int`.  Packing and unpacking works that same as with `struct`.
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

As a final note, if your custom type is representing an integer, make sure to implement a `__index__` so it can be packed with `struct`.  Similarly, if it is representing a float, make sure to implement a `__float__`.  For `bytes` wrappers, unfortunately `struct` does not call `__bytes__` on the unerlying object.  Your options in that case are to base your class on `bytes` (forcing it to be immutable), or to write a `Serializer` for it.  You can take a look at `complex_types/strings.py` for some ideas on how to do that.

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
In this example, `Derived` now treats `a` as an `int16`, and ignores `b` completely when it comes to packing/unpacking.  The format string for `Derived` is now `'hif'` (`a: int8`, `c: int32`, `d: float32`).

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

You can also access the `attrs` class attribute, which is the attribute names handled by the class's serializer, in the order they are packed/unpacked.

For more advanced work, it is recommended to rework your class layout, or write your own custom `Serializer` class and annotate your types with it (See: structured/base_types.py for more information on the Serializer API).  In the case this is still not enough, you have access to two builder methods:

- `structured.create_serializer`: This is used internally to create the serializers on the classes themselves.  You can call it with a typehints dictionary, and a byte order to use.  You can optionally pass in a second typhints-like dictionary to override anything in the typehints dictionary (this is only used in class creation, it should not be necessary in most cases).  The method returns back a `Serializer` instance, along with a tuple of attribute names the serializer packs and unpacks.
- `Structured.create_attribute_serializer`: You can call this with attribute names on a `Structured` class to get a serializer which can pack and unpack the given attributes on the class.  Note that at the moment there is little sanity checking.  The resulting serializer will be set up to pack/unpack the given attributes *in the order they are defined on the class*.  Any gaps in the attribute layout are up to you to handle.

In the instance you find yourself working with a common pattern that is not handled easily by the built in features of `structured`, feel free to open a feature request!


### Packing / Unpacking methods
`Structured` classes provide a couple of ways to pack and unpack their values:
 - `Structured.unpack(byteslike)`: Unpacks values from a bytes-like object and sets the instance's variables.
 - `Structured.unpack_from(buffer, offset = 0)`: Unpacks values from an object supporting the [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html) and sets the instance's variables.
 - `Structured.unpack_read(readable)`: Reads data from a file-like object, unpacks, and sets the instance's variables.
 - `Structured.pack()`: Packs the instance's variables, returning `bytes`.
 - `Structured.pack_int(buffer, offset = 0)`: Packs the instance's variables into an object supporting the [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html).
 - `Structured.create_unpack(byteslike)`: Creates new object with values unpacked from a bytes-like object.
 - `Structured.create_unpack_from(buffer, offset = 0)`: Creates a new object with values unpacked from an object supporting the [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html).
 - `Structured.create_unpack_read(readable)`: Creates a new object with values unpacked from a readable file-like object.


## Advanced types
Structured also supports a few more complex types that require extra logic to pack and unpack.  These are:
- `char`: For unpacking binary blobs whose size is not static, but determined by data just prior to the blob (yes, it's also a basic type).
- `unicode`: For strings, automatically encoding for packing and decoding for unpacking.
- `array`: For unpacking multiple instances of a single type.  The number to unpack may be static or, like `blob`, determined by data just prior to the array.


### String types
There are two string types, `char` and `unicode`, with four ways to specify their length (in bytes):
- `char`: A bare `char` or `unicode` specifies unpacking a single byte.
- `char[5]`: Specifying an integer unpacks a fixed sized `bytes` (for `char`) or `str` (for `unicode`).
- `char[uint8]`: Specifying one of `uint8`, `uint16`, `uint32`, or `uint64` causes unpacking fist the specified integers, which denotes the length in bytes of the `char` or `unicode` string to unpack.
- `char[b'\0']`: Specifying a single byte indicates a terminated string.  Data will be unpacked until the delimiter is encountered.  As a quick alias, you can use `null_char` and `null_unicode` for a null-terminated `bytes` or `str`, respectively.  Packing terminated strings will automatically add the terminator if missing, and unpacking will fail if the terminator is not encountered.

The difference between `char` and `unicode` is that `unicode` objects will automatically encode/decode the string for you.  You can specify one of the built-in encodings as a second argument to `unicode`: `unicode[10, 'ascii']`, or if needed code your own `EncoderDecoder` class to provide the encoding and decoding methods.  The default encoding if not specified is `'utf8'`.


### `array`
Arrays allow for reading in mutiple instances of one type.  These types may be any of the other basic types (except `char`, and `pascal`), or a `Structured` type.  Arrays can be used to support data that is structured in one of five ways.  First specify a `Header` which determines how the length is determined, and optionally any size check bytes, then specify a data type held by the `array`:
- `array[Header[10], int8]`: A static number (`10`) of basic items (`int8`).  Array length will be checked on writing.
- `array[Header[uint32], int8]`: A dynamic number of basic items (`int8`).  Array length is determined by unpacking a `uint32` first.
- `array[Header[3], MyStruct]`: A static number (`3`) of `Structured` derived items (`MyStruct` instances).  Array length will be checked on writing.
- `array[Header[uint8], MyStruct]`: A dynamic number of `Structured` derived items (`MyStruct` instances).  Array length is determined by unpacking a `uint8` first.
- `array[Header[uint8, uint32], MyStruct]`: A dynamic number of `Structured` derived items (`MyStruct` instances).  Array length is determined by unpacking a `uint8` first, and directly after a `uint32` is unpacked which holds the number of bytes which hold the actual `Structured` items (not including the header size).  This size is checked on unpacking.
NOTE: Only arrays holding `Structured` items currently support the optional data size unpacking in the `Header`.

For example, suppose you know there will always be 10 `uint8`s in your object and you want them in an array:
```python
class MyStruct(Structured):
  items: array[Header[10], uint8]
```

Or if you need to unpack a `uint32` to determine the number of items, then a `uint32` to detemine the data size of the array, each item holding a `uint8` and a `uint16`:
```python
class MyItem(Structured):
  first: int8
  second: uint16

class MyStruct(Structured):
  ten_items: array[Header[10, uint32], MyItem]
```


## Notes of type checkers / IDEs
For the most part, `structured` should work with type checkers set to basic levels.  The annotated types present as their unpacked types with a few exceptions.  This is accomplised by using `typing.Annotated`.
- `int*` and `uint*` present as an `int`
- `float*` present as `float`.
- `bool8` presents as `int`.  This may change to `bool` in the future, but it's this way currently because the `?` format specifier packs/unpacks as an `int`.
- `char` and `pascal` are subclasses of `bytes`, so they have the typechecker limitations below.
- `array[Header[...], T]` is a subclass of `list[T]`, so it has the typechecker limitations below.
- `unicode` is a subclass of `str`, so it has the typechecker limitations below.

The limitations for types that are subclasses of their intended type, rather than `typing.Annotated` as such, is most typecheckers will warn you about assignment.  For example:
```python
class MyStruct(Structured):
  items: array[Header[3], int8]

a = MyStruct([1, 2, 3])
a.items = [4, 5, 6]   # Warning about incompatibility between list and array
```

To resolve this, you will have to use an alternative syntax: `typing.Annotated`:
```python
class MyStruct(Structured):
  items: Annotated[list[int8], array[Header[3], int8]]

a = MyStruct([1, 2, 3])
a.items = [4, 5, 6]   # Ok!
```

NOTE: In older versions, it was recommened to use `serialized`.  This method has been deprecated and will be removed in `3.0`.


## Generic `Structured` classes
You can also create your `Structured` class as a `typing.Generic`.  Due to details of how `Generic` works, to get a working specialized version, you must subclass the specialization:

```python
class MyGeneric(Generic[T, U], Structured):
  a: T
  b: list[U] = Annotated[list[U], array[Header[10], U]]


class ConcreteClass(MyGeneric[uint8, uint32]): pass
```

One **limitation** here however, you cannot use a generic Structured class as an array object type (as expected at least).  It will act as the base class without specialization (See #8).  So for example, the following code will not work as you expect:
```python
class Item(Generic[T], Structured):
  a: T

class MyStruct(Generic[T], Structured):
  items: array[Header[10], Item[T]]

class Concrete(MyStruct[uint32]): pass

obj = Concrete.unpack(data)
assert hasattr(obj.items[0], 'a')

> AssertionError
```


## Dataclass compatibility
For the most part, `Structured` should be compatible with the `@dataclass`
decorator.  To suppress the generated `__init__` method and use `@dataclass`s
instead, pass `init=False` to the subclassing machinery.

NOTE: The unpacking logic requires your class's `__init__` to accept at least
all of the unpacked fields in order as arguments, so if you want to write your
own or use `@dataclass`s, make sure to mark other types as non-initialization
variables (with `= field(init=False)`).  You can further initialize those
variables in a `__post_init__` method.

Here's an example of mixing both `structured` types and other types, as well as
using `@dataclass`s generated `__init__`:

```python
@dataclass
class MyStruct(Structured, init=False):
  a: int8
  b: int = field(init=False)
  _: pad[1] = field(init=False)
  c: uint16

  def __post_init__(self) -> None:
    self.b = 0

data = struct.pack('bH', 1, 42)
a = MyStruct.create_unpack(data)
print(a)

> MyStruct(a=1, c=42)
```
