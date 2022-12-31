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
| `c`             | equivalent to `char[1]` | `bytes` with length 1 | |
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
 1. These type must be indexed to specify their length.  For a single byte `char` for example (`'s'`), use `char[1]`.
 2. The 16-bit float type is not supported on all platforms.
 3. `struct` treats `bool` as an `int`, so this is implemented as an `int`.  Packing and unpacking works that same as with `struct`.
 4. Pad variables are skipped and not actually assigned when unpacking, nor used when packing.  There is a special metaclass hook to allow you to name all of your pad variables `_`, and they still **all** count towards the final format specifier.  If you want to be able to override their typehint in subclasses, choose a name other than `_`.

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
Sometimes, the provided types are not enough.  Maybe you have a mutable type that encapsulates an integer.  To enable your type to work with `Structured` as a type annotation, you can specify how it should be serialized by referencing one of the basic types.  A restriction here is that basic type must unpack as a single value (so for example, `pad` is not allowed). To communicate this information to `Structured`, use `typing.Annotated` and `structured.SerializeAs`:

```python
class MyInt:
  _wrapped: int
  def __init__(self, value: int) -> None:
    self._wrapped = value

  def __index__(self) -> int:
    return self._wrapped

class MyStruct(Structured):
  version: Annotated[MyInt, SerializeAs(int32)]
```

If you use your type a lot, you can use a `TypeAlias` to make things easier:

```python
MyInt32: TypeAlias = Annotated[MyInt, SerializeAs(int32)]

class MyStruct(Structured):
  version: MyInt32
```

Finally, if you're missing some of the old functionality of `Formatted` (versions 2 of `structured`), you could write your own `__class_getitem__`:
```python
class MyInt:
  ...

  def __class_getitem__(cls, key) -> type[Self]:
    return Annotated[cls, SerializeAs[key]]
```

As a final note, if your custom type is representing an integer, make sure to implement a `__index__` so it can be packed with `struct`.  Similarly, if it is representing a float, make sure to implement a `__float__`.  For `bytes` wrappers, unfortunately `struct` does not call `__bytes__` on the unerlying object.  Your options in that case are to base your class on `bytes` (forcing it to be immutable), or to write a `Serializer` for it.  You can take a look at `complex_types/strings.py` for some ideas on how to do that.

If your type is more complicated, you can define a `Structured` derived class for it, then hint with that class:

```python
class MyItem(Structured):
  a: uint32
  b: float32

class MyStruct(Structured):
  sig: char[4]
  item: MyItem
```

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

For more advanced work, it is recommended to rework your class layout, or write your own custom `Serializer` class and annotate your types with it (See: structured/base_types.py for more information on the Serializer API).

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
- Unions: For types that could unpack as many different types, depending on certain conditions.


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

### Unions
Sometimes, the data structure you're packing/unpacking depends on certain conditions.  Maybe a `uint8` is used to indicate what follows next.  In cases like this, `Structured` supports unions in its typehints.  To hint for this, you need two things:
1. Every type in your union must be a serializable type (either one of the provided types, or a `Structured` derived class)
2. You need to configure how to decide which type to unpack/pack as, with a decider.

#### Deciders
All deciders provide some method to take in information and produce a value to be used to make a dicision.  The decision is made with a "decision map", which is a mapping of value to serialization types.  You can also provide a default serialization type, or `None` if you want an error to be raised if your decision method doesn't produce a value in the decision map.

For `LookbackDecider`, you provide a method that accepts an object, and produces a value.  The object will be a `Structured`-like object with all currently unpacked values set to the applicable attributes (in some cases, this actually *is* the `Structured` object being packed/unpacked).  A common method to use for this decider is `operator.attrgetter`.

For `LookaheadDecider`, the functionality differs between packing and unpacking.  For unpacking, you must specify a serializable type that will be unpacked first, then sent to the decision map.  For packing, you must provide a write deciding method, which acts in the same was as `LookbackDecider`'s decision method.

Here are a few examples:
```python
class MyStruct(Structured):
  a_type: uint8
  a: uint32 | float32 | char[4] = config(LookbackDecider(attrgetter('a_type'), {0: uint32, 1: float32}, char[4]))
```
This example first unpacks a `uint8` and stores it in `a_type`.  The union `a` polls that value with `attrgetter`, if the value is 0 it unpacks a `uint32` for `a`.  If the value is 1, it unpacks a `float32`, and if it is anything else it unpacks just 4 bytes (raw data).

```python
class IntRecord(Structured):
  sig: char[4]
  value: int32

class FloatRecord(Structured):
  sig: char[4]
  value: float32

class MyStruct(Structured):
  record: IntRecord | FloatRecord = config(LookaheadDecider(char[4], attrgetter('record.sig'), {b'IIII': IntRecord, 'FFFF': FloatRecord}, None))
```
For unpacking, this example first reads in 4 bytes (`char[4]`), then looks up that value in the dictionary.  If it was `b'IIII'`, then it rewinds and unpacks an `IntRecord` (note: `IntRecord`'s `sig` attribute will be set to `char[4]`.)  If it was `b'FFFF'` it rewinds and unpacks a `FloatRecord`, and if was neither it raises an exception.

For packing, this example uses `attrgetter('record.sig')` on the object to decide how to pack it.



## Notes of type checkers / IDEs
For the most part, `structured` should work with type checkers set to basic levels.  The annotated types present as their unpacked types with a few exceptions.  This is accomplished by using `typing.Annotated`.
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
all of the unpacked fields, *in order*, as arguments. Any extra arguments must
have defaults supplied. So if you want to write your own or use `@dataclass`s,
make sure to mark other types as non-initialization variables
(with `= field(init=False)`). You can further initialize those variables in a
`__post_init__` method.

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
