![tests](https://github.com/lojack5/structured/actions/workflows/tests.yml/badge.svg)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![pypi](https://img.shields.io/pypi/v/structured-classes)](https://pypi.org/project/structured-classes/)

Version 3.1.x is the last version to support Python 3.9.

# structured - creating classes which pack and unpack with Python's `struct` module.
This is a small little library to let you leverage type hints to define classes which can also be packed and unpacked using Python's `struct` module.  The basic usage is almost like a dataclass:


```python
class MyClass(Structured):
  file_magic: char[4]
  version: uint8

a = MyClass(b'', 0)

Get it on PypI

with open('some_file.dat', 'rb') as ins:
  a.unpack_read(ins)
```

# Contents

1. [Hint Types](#hint-types): For all the types you can use as type-hints.
    - [Basic Types](#basic-types)
    - [Complex Types](#complex-types)
    - [Custom Types](#custom-types)
    - [Modifiers](#modifiers)
2. [The `Structured` class](#the-structured-class)
3. [Generics](#generics)
4. [Serializers](#serializers)


# Hint Types
If you just want to use the library, these are the types you use to hint your instance variables to
make them detected as serialized by the packing/unpacking logic. I'll use the term **serializable**
to mean a hinted type that results in the variable being detected by the `Structured` class as being
handled for packing and unpacking. They're broken up into two basic
catergories:
- Basic Types: Those with direct correlation to the `struct` format specifiers, needing no extra
  logic.
- Complex Types: Those still using `struct` for packing and unpacking, but requiring extra logic
  so they do not always have the same format specifier.
- Custom Types: You can use your own custom classes and specify how they should be packed and
  unpacked.


Almost all types use `typing.Annotated` under the hood to just add extra serialization information
to the type they represent. For example `bool8` is defined as
`Annotated[bool8, StructSerializer('?')]`, so type-checkers will properly see it as a `bool`.

There are four exceptions to this.  For these types, almost everything should pass inspection by a
type-checker, except for assignment.  These are:
- `char`: subclassed from `bytes`.
- `pascal`: subclassed from `bytes`.
- `unicode`: subclassed from `str`.
- `array`: subclassed from `list`.

If you want to work around this, you can use `typing.Annotated` yourself to appease the
type-checker:

```python
class MyStruct1(Structured):
  name: unicode[100]

item = MyStruct('Jane Doe')
item.name = 'Jessica'   # Type-checker complains about "str incompatible with unicode".

class MyStruct2(Structured):
  name: Annotated[str, unicode[100]]

item = MyStruct('Jane Doe')
item.name = 'Jessica'   # No complaint from the type-checker.
```


## Basic Types
Almost every format specifier in `struct` is supported as a type:

| `struct` format | structured type | Python type | Notes |
|:---------------:|:---------------:|-------------|:-----:|
| `x`             | `pad`           |             |(1)(3) |
| `c`             | equivalent to `char[1]` | `bytes` with length 1 | |
| `?`             | `bool8`         | `int`       |       |
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
 1. These type must be indexed to specify their length.  For a single byte `char` for example
    (`'s'`), use `char[1]`.
 2. The 16-bit float type is not supported on all platforms.
 3. Pad variables are skipped and not actually assigned when unpacking, nor used when packing. There
    is a special metaclass hook to allow you to name all of your pad variables `_`, and they still
    **all** count towards the final format specifier.  If you want to be able to override their
    type-hint in subclasses, choose a name other than `_`.

Consecutive variables with any of these type-hints will be combined into a single `struct` format
specifier.  Keep in mind that Python's `struct` module may insert extra padding bytes *between*
(but never before or after) format specifiers, depending on the Byte Order specification used.

Example:

```python
class MyStruct(Structured):
  a: int8
  b: int8
  c: uint32
  _: pad[4]
  d: char[10]
  _: pad[2]
  e: uint32
```
In this example, all of the instance variables are of the "basic" type, so the final result will be
as if packing or unpacking with `struct` using a format of `2bI4x10s2xI`.  Note we took advantage of
the `Structured` metaclass to specify the padding using the same name `_`.


### Byte Order
All of the specifiers are supported, the default it to use no specifier:
| `struct` specifier | `ByteOrder` |
|:------------------:|:-----------:|
| `<`                | `LITTLE_ENDIAN` (or `LE`) |
| `>`                | `BIG_ENDIAN` (or `BE`) |
| `=`                | `NATIVE_STANDARD` |
| `@`                | `NATIVE_NATIVE` |
| `!`                | `NETWORK`   |

To specify a byte order, pass `byte_order=ByteOrder.<option>` to the `Structured` sub-classing
machinery, like so:

```python
class MyStruct(Structured, byte_order=ByteOrder.NETWORK):
  a: int8
  b: uint32
```
In this example, the `NETWORK` (`!`) specifier was used, so `struct` will not insert any padding
bytes between variables `a` and `b`, and multi-byte values will be unpacked as Big Endian numbers.


## Complex Types
All other types fall into the "complex" category.  They currently consist of:
- `tuple`: Fixed length tuples of serializable objects.
- `array`: Lists of a single type of serializable object.
- `char`: Although `char[3]` (or any other integer) is considered a basic type, `char` also supports
  variable length strings.
- `unicode`: A wrapper around `char` to add automatic encoding on pack and decoding on unpack.
- `unions`: Unions of serializable types are supported as well.
- `Structured`-derived types: You can use any of your `Structured`-derived classes as a type-hint,
  and the variable will be serialized as well.
- `typing.Self`: This type-hint denotes that the attribute should be unpacked as an instance of
  the containing class itself.  Note that due to the recursive posibilities this allows, care
  must be taken to avoid hitting the recursion limit of Python.


### Tuples
Both the `tuple` and `Tuple` type-hints are supported, including `TypeVar`s (see: `Generics`). To be
detected as serializable, the `tuple` type-hint must be for a fixed sized `tuple` (so no elipses
`...`), and each type-hint in the `tuple` must be a serializable type.

Example:
```python
class MyStruct(Structured):
  position: tuple[int8, int8]
  size: tuple[int8, int8]
```

### Arrays
Arrays are `list`s of one kind of serializable type. You do need to specify how `Structured` will
determine the *length* of the list when unpacking, and how to write it when packing. To do this,
you chose a `Header` type. The final type-hint for your list then becomes
`array[<header_type>, <item_type>]`. Arrays also support `TypeVar`s.

Here are the header types:
- `Header[3]` (or any other positive integer): A fixed length array. No length byte is packed or
  unpacked, just the fixed number of items. When packing, if the list doesn't contain the fixed
  number of elements specified, a `ValueError` is raised.
- `Header[uint32]` (or any other `uint*`-type): An array with the length stored as a `uint32` (or
  other `uint*`-type) just before the items.
- `Header[uint32, uint16]`: An array with two values stored just prior to the items. The first
  value (in this case a `uint32`) is the length of the array. The second value (in this case a
  `uint16`) denotes how many bytes of data the array items takes up. When unpacking, this size is
  checked against how many bytes were actually required to unpack that many items. In the case of a
  mismatch, a `ValueError` will be raises.

Example:
```python
class MyItem(Structured):
  name: unicode[100]
  age: uint8

class MyStruct(Structured):
  students: array[Header[uint32], MyItem]
```


### `char`
For unpacking bytes other than with a fixed length, you have a few more options with `char`:
- `char[uint8]` (or any other `uint*` type): This indicates that a value (a `uint8` in this case)
  will be packed/unpack just prior to the `bytes`.  The value holds the number of `bytes` to pack or
  unpack.
- `char[b'\0']` (or any other single bytes): This indicates a terminated byte-string. For
  unpacking, bytes will be read until the terminator is encountered (the terminator will be
  discarded). For packing, the `bytes` will be written, and a terminator will be written at the end
  if not already written.  The usual case for this is NULL-terminated byte-strings, so a quick alias
  for that is provided: `null_char`.
- `char[math.inf]`: This indicates that every remaining byte in the input stream should be unpacked
  (read to the end). Note that this means no other serialized types can occur after this item.
- `unicode[math.inf]`: Like `char[math.inf]`, but the bytes are then decoded into a string.


### `unicode`
For cases where you want to read a byte-string and treat it as text, `unicode` will automatically
encode/decode it for you.  The options are the same as for `char`, but with an optional second
argument to specify how to encode/decode it.  The second option can either be a string indicating
the encoding to use (defaults to `utf8`), or for more complex solutions you may provide an
`EncoderDecoder` class.  Similar to `char`, we provide `null_unicode` as an alias for
`unicode[b'\0', 'utf8']`.

```python
class MyStruct(Structured):
  name: null_unicode
  description: unicode[255, 'ascii']
  bio: unicode[uint32, MyEncoderDecoder]
```

To write a custom encoder-decoder, you must subclass from `EncoderDecoder` and implement the two
class methods `encode` and `decode`:

```python
class MyEncoderDecoder(EncoderDecoder):
  @classmethod
  def encode(text: str) -> bytes: ...

  @classmethod
  def decode(bytestring: bytes) -> str: ...
```


### Unions
Sometimes, the data structure you're packing/unpacking depends on certain conditions.  Maybe a
`uint8` is used to indicate what follows next.  In cases like this, `Structured` supports unions in
its typehints.  To hint for this, you need to do three things:
1. Every type in your union must be a serializable type.
2. You need create a *decider* which will perform the logic on deciding how to unpack the data.
3. Use `typing.Annotated` to indicate the decider to use for packing/unpacking.

#### Deciders
All deciders provide some method to take in information and produce a value to be used to make a
decision. The decision is made with a "decision map", which is a mapping of value to serializable
types. You can also provide a default serializable type, or `None` if you want an error to be raised
if your decision method doesn't produce a value in the decision map.

There are currently two deciders.  In addition to the decision map and default, you will need to
provide a few more things for each:
- `LookbackDecider`: You provide a method that accepts the object to be packed/unpacked and produces
  a decision value.  Commonly, `operator.attrgetter` is used here.  A minor detail: for unpacking
  operations, the object sent to your method will not be the actual unpacked object, merely a proxy
  with the values unpacked so far set on it.
- `LookaheadDecider`: For packing, this behaves just like `LookbackDecider`.  For unpacking, you
  need to specify a serializable type which is unpacked first and used as the the value to look up
  in the decision map.  After this first value is unpacked, the data-stream is rewound back for
  unpacking the object.

Here are a few examples:
```python
class MyStruct(Structured):
  a_type: uint8
  a: Annotated[uint32 | float32 | char[4], LookbackDecider(attrgetter('a_type'), {0: uint32, 1: float32}, char[4])]
```
This example first unpacks a `uint8` and stores it in `a_type`. The union `a` polls that value with
`attrgetter`, if the value is 0 it unpacks a `uint32`, if it is 1 it unpacks a `float32`, and if it
is anything else it unpacks just 4 bytes (raw data), storing whatever was unpacked in `a`.

```python
class IntRecord(Structured):
  sig: char[4]
  value: int32

class FloatRecord(Structured):
  sig: char[4]
  value: float32

class MyStruct(Structured):
  record: Annotated[IntRecord | FloatRecord, LookaheadDecider(char[4], attrgetter('record.sig'), {b'IIII': IntRecord, 'FFFF': FloatRecord}, None)]
```
For unpacking, this example first reads in 4 bytes (`char[4]`), then looks up that value in the
dictionary. If it was `b'IIII'` then it rewinds and unpacks an `IntRecord` (note: `IntRecord`'s
`sig` attribute will be set to `char[4]`). If it was `b'FFFF'` it rewinds and unpacks a
`FloatRecord`, and if was neither it raises an exception.

For packing, this example uses `attrgetter('record.sig')` on the object to decide how to pack it.


### Structured
You can also type-hint with one of your `Structured` derived classes, and the value will be unpacked
and packed just as expected.  `Structured` doesn't *fully* support `Generic`s, so make sure to read
the section on that to see how to hint properly with a `Generic` `Structured` class.

Example:
```python
class MyStruct(Structured):
  a: int8
  b: char[100]

class MyStruct2(Structured):
  magic: char[4]
  item: MyStruct
```


## Custom Types
When the above are not enough, and your problem is fairly simple, you can use `SerializeAs` to tell
the `Structured` class how to pack and unpack your custom type. To do so, you choose one of the
above "basic" types to use as its serialization method, then type-hint with `typing.Annotated` to
provide that information via a `SerializeAs` object.

For example, say you have a class that encapsulates an integer, providing some custom functionality.
You can tell your `Structured` class how to pack and unpack it. Say the value will be stored as a
4-byte unsigned integer:

```python
class MyInt:
  _wrapped: int

  def __init__(self, value: int) -> None:
    self._wrapped = value

  def __index__(self) -> int:
    return self._wrapped

class MyStruct(Structured):
  version: Annotated[MyInt, SerializeAs(uint32)]
```

If you use your type a lot, you can use a `TypeAlias` to make things easier:

```python
MyInt32: TypeAlias = Annotated[MyInt, SerializeAs(int32)]

class MyStruct(Structured):
  version: MyInt32
```

Note a few things required for this to work as expected:
- Your class needs to accept a single value as its initializer, which is the value unpacked by the
  serializer you specified in `SerializeAs`.
- Your class must be compatible with your chosen type for packing as well.  This means:
  - for integer-like types, it must have an `__index__` method.
  - for float-like types, it must have a `__float__` method.

Finally, if the `__init__` requirement is too constraining, you can supply a factory method for
creating your objects from the single unpacked value, and use `SerializeAs.with_factory` instead.
The factory method must accept the single unpacked value, and return an instance of your type.


## Modifiers
These are additional objects that you can include in an `Annotated[...]` to modify how a hinted serialized type is packed/unpacked. Currently, there is only `Condition`.

### `Condition`
The `Condition` object signals to `Structured` that the hinted attribute should only be considered a serializable type if a certain condition is met. For example, a data structure that has fields added or removed as new versions are made. You could provide different  Structured`-derived classes for these versions, but this opens you up to errors resulting from keeping those definition in sync with each other.

To use, create a `Condition` object:
```python
# NOTE: using Python 3.11+ syntax to demonstrate the signature here
Condition[T: Structured](condition: Callable[[T], bool], *defaults)
```

and include it in an `Annotated[...]` for a serializable type:
```python
class VersionedStruct(Structured, byte_order=ByteOrder.NETWORK):
  version: uint8
  v1_field: Annotated[uint8, Condition(lambda s: s.version >= 1, 0)]
  v3_field: Annotated[uint32, Condition(lambda s: s.version >= 3, 0)]
  v2_field: Annotated[float32, Condition(lambda s: s.version >= 3, 0.0)]
```

A `Condition` takes a callable that accepts your `Structured` class\* and returns a `bool`, as well as a default value for the attribute. The callable will be called just prior to packing/unpacking the attribute to evaluate the condition. On a `True` condition valuation, the attribute will pack/unpack\* as if hinted without the `Condition`. On a `False` condition evaluation, the attribute will be skipped for packing, or set to the default value (without touching the input data stream).

> [!NOTE]
> For unpacking, the object sent to the condition is actually a proxy object. This object has the > same serialized attributes as the actual `Structured`-derived class, but only those that have > already been de-serialized.

> [!CAUTION]
> For simple types (those that have direct `struct.pack` translations) some care is needed.

Recall that `struct` inserts padding alignment bytes where needed between format specifiers. So for example:
```python
>>> struct.pack('BI', 1, 2)
b'\x01\x00\x00\x00\x02\x00\x00\x00`
```
Here, 3 padding bytes were inserted between the `uint8` and the `uint16`. The padding inserted depends on the platform and the byte-order specifier used.

Now consider these two `Structured` classes:
```python
class MyStruct1(Structured):
  version: uint8
  value: uint32

class MyStruct2(Structured):
  version: uint8
  value: Annotated[uint32, Condition(lambda s: True, 0)]
```
These two classes will not, in general, pack/unpack the same, even though the `Condition` is always True! This is because for `MyStruct1`, the members are serialized as `BI`. But for `MyStruct2`, they are serialized as `B` followed by `I`, so no padding bytes are inserted ever.

To deal with situations like these, you either need to manually handle the padding bytes yourself (also guarded with a `Condition`), or if possible use a byte order specification that does not insert padding bytes (for example, `ByteOrder.NETWORK`).


## The `Structured` class
The above examples should give you the basics of defining your own `Structured`-derived class, but
there are a few details and you probably want to know, and *how* to use it to pack and unpack your
data.


### dunders
- `__init__`: By default, `Structured` generates an `__init__` for your class which requires an
  initializer for each of the serializable types in your definition. You can block this generated
  `__init__` by passing `init=False` to the subclassing machinery. Keep in mind, whatever you
  decide the final class's `__init__` must be compatible with being initialized in the original way
  (one value provided for each serializable member). Otherwise your class cannot be used as a
  type-hint or as the item type for `array`.
- `__eq__`: `Structured` instance can be compared for equality / inequality.  Comparison is done by
  comparing each of the instance variables that are serialized.  You can of course override this
  in your subclass to add more checks, and allow `super().__eq__` to handle the serializable types.
- `__str__`: `Structured` provides a nice string representation with the values of all its
  serializable types.
- `__repr__`: The repr is almost identical to `__str__`, just with angled brackets (`<>`).

### Class variables
There are three public class variables associated with your class:
- `.serializer`: This is the **serializer** (see: Serializers) used for packing and unpacking the
  instance variables of your class.
- `.byte_order`: This is a `ByteOrder` enum value showing the byte order and alignment option used
  for your class.
- `.attrs`: This is a tuple containing the names of the attributes which are serialized for you, in
  the order they were detected as serializable.  This can be helpful when troubleshooting why your
  class isn't working the way you intended.

### Packing methods
There are three ways you might pack the data contained in your class, two should be familiar from
Python's `struct` library:
- `pack() -> bytes`: This just packs your data into a bytestring and returns it.
- `pack_into(buffer, offset = 0) -> None`: This packs your data into an object supporting the
  [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html), starting at the given offset.
- `pack_write(writable) -> None`: This packs your data, writing to the file-like object `writable`
  (which should be open in binary mode).


### Unpacking methods
Similar to packing, there are three methods for unpacking data into an already existing instance of
your class. There are also three similar class methods for creating a new object from freshly
unpacked data:
- `unpack(buffer) -> None`: Unpacks data from a bytes-like buffer, assigning values to the instance.
- `unpack_from(buffer, offset=0) -> None`: Like `unpack`, but works with an object supporting the
  [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html).
- `unpack_read(readable)`: Reads data from a file-like object (which should be open in binary mode),
  unpacking until all instance variables are unpacked.
- `create_unpack(buffer) -> instance`: Class method that unpacks from a bytes-like buffer to create
  a new instance of your class.
- `create_unpack_from(buffer, offset=0) -> instance`: Class method that unpacks from a buffer
  supporting the [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html) to create a new
  instance of your class.
- `create_unpack_read(readable) -> instance`: Class method that reads data from a file-like object
  until enough data has been processed to create a new instance of your class.


### Subclassing
Subclassing from your `Structured`-derived class is very straight-forward. New members are inserted
after previous one in the serialization order. You can redefine the type of a super-class's member
and it will not change the order. For example, you could remove a super-class's serializable member
entirely from serialization, by redefining its type-hint with `None`.

Multiple inheritance from `Structured` classes is not supported (so no diamonds). By default, your
sub-class must also use the same `ByteOrder` option as its super-class. This is to prevent
unintended serialization errors, so if you really want to change the `ByteOrder`, you can pass
`byte_order_mode=ByteOrderMode.OVERRIDE` to the sub-classing machinery.


An example of using a different byte order than the super-class:
```python
class MyStructLE(Structured, byte_order=ByteOrder.LE):
  a: int8
  b: int32

class MyStructBE(MyStructLE, byte_order=ByteOrder.BE, byte_order_mode=ByteOrderMode.OVERRIDE):
  pass
```

A simple example of extending:
```python
class MyStructV1(Structured):
  size: uint32
  a: int8
  b: char[100]

class MyStructV2(MyStructV2):
  c: float32
```
Here, the sub-class will pack and unpack equivalent to the `struct` format `'Ib100sf'`.

A an example of removing a member from serialization:
```python
class MyStruct(Structured):
  a: int8
  b: uint32
  c: float32

class DerivedStruct(MyStruct):
  b: None
```
Here, the sub-class will pack and unpack equivalent to the `struct` format `'bf'`.


### Generics
`Structured` classes can be used with `typing.Generic`, and most things will work the way you want,
with an extra step needed in one case. The `Structured` class behaves this way so as not to
interfere with the `typing` module's usual features. A "bare" specialization of your class will act
in the usual way all `typing.Generic` subclasses do: you can use `get_origin`, `get_args`, etc on it
as usual.

In general, in order for your `Structured` class to "know" about the specialization arguments you
pass to it and work based of that specialization, it must be subclassed.  In many common cases this
subclassing will be done for you though.  If the `TypeVar` specialization happens *within* another
`Structured` class, then you don't need to sub-class it yourself.  Even in this case, the type-hints
are not modified on the class itself, so you can do any type-hint introspection you want and they
will still behave the usual way the `typing` module would expect.

Here's some examples to show what I mean by the specialization occuring "within" versus not:

```python
class Inner(Generic[T, U, V], Structured):
  a: tuple[T]
  b: U
  c: array[Header[4], V]
```
Here, `Inner` is a generic `Structured` class, and hasn't yet been specialized at all.  So all of
its type-hints are *not* detected as serializable types.

An example of specializing this class "outside" of the class looks like this:

```python
unhappy_object = Inner[int8, float32, bool8].create_unpack(data)
```

In this case, `Inner` gets fully specialized, but still acts exactly as `typing.Generic` usually
does: nothing new happens.  The `unhappy_object` gets unpacked just as if you'd never specialized
`Inner` at all (so it has no attributes serialized). To make an instance of
`Inner[int8, float32, bool8]`, you'd have to do this:

```python
class ConcreteInner(Inner[int8, float32, bool8]):
  pass
happy_object = ConcreteInner.create_unpack(data)
```

An example of specializing this class "inside" of another `Structured class looks like this:

```python
class Outer(Structured):
  sub_item: Inner[int8, float32, bool8]
happy_object = Outer.create_unpack(data)
```

Here, because the specialized `Inner` was used as a type-hint within another `Structured` class,
and the `TypeVar`s are fully specialized, everything works exactly how you'd want.  The `sub_item`
instance variable correctly has all of it's attributes (a, b, and c) unpacked as a `tuple[in8]`, a
`float32`, and a `array[Header[4], bool8]` respectively.

Here's one last example of where this automatic subclassing behavior *doesn't* kick in:

```python
class Outer2(Generic[T], Structured):
  sub_item: Inner[int8, float32, T]
unhappy_object = Outer2[bool8].create_unpack(data)
```

Here again, `Outer2` is generic and not fully specialized *within* another `Structured` class so
you'd have to subclass it yourself.  But again, if you use `Outer2` as a fully specialized type-hint
within another `Structured` class you're good to go with no extra work.

In general:
- If the outer-most `Structured` is `Generic`, than any `TypeVar`s it uses will *not* be
  automatically detected for serialization, even when specialized.  You *must* sub-class it yourself
  to get the final implementation.  Of course, if those `TypeVar`s are never intended to be
  serializable types (maybe you're using the `TypeVar` for a completely unrelated purpose) then
  this doesn't really matter.
- If the outer-most `Structured` class doesn't use `TypeVar`s (isn't `Generic` itself), then
  everything will automatically be handled for you.


## Serializers
For those more interested in what goes on under the hood, or need more access to implement
serialization of a custom type, read on to learn about what **serializers** are and how they work!

Serializers are use `typing.Generic` and `typing.TypeVarTuple` in their class heirarchy, so if you
want to include the types the serializer unpacks this *could* help find errors.  For example:

```python
class MySerializer(Serializer[int, int, float]):
  ...
```
would indicate that this serializer packs and unpacks three items, an `(int, int float)`.

### The API
The `Serializer` class exposes a public API very similar to that of `struct.Struct`. All of these
methods must be implemented (unless noted otherwise) in order to work fully.

#### Attributes
- `.num_values: int`: In most cases this can just be a class variable, this represents the number of
  items unpacked or packed by the serializer.  For example, a `StructSerializer('2I')` has
  `num_values == 2`.  Note that `array` has `num_values == 1`, since it unpacks a *single* list.
- `.size`: This is similar to `struct.Struct.size`.  It holds the number of bytes required for a
  pack or unpack operation. However unlike `struct.Struct`, the serializer may not know this size
  until the item(s) have been fully packed or unpacked. For this reason, the `.size` attribute is
  only required to be up to date with the most recently completed pack or unpack call.

#### Packing methods
- `.prepack(self, partial_object) -> Serializer` (**not required**): This will be called just prior
  to any of the pack methods of the `Serializer`, with a (maybe proxy of) the `Structured` object to
  be packed. This is to allow union serializers (for example) to make decisions based on the state
  of the object to be packed.  This method should return an appropriate serializer to be used for
  packing, based on the information contained in `partial_object`.  In most cases, the default
  implementation will do just fine, which just returns itself unchanged.
- `.pack(self, *values) -> bytes`: Pack the values according to this serializer's logic. The number
  of items in `values` must be `.num_values`.  Return the values in packed `bytes` form.
- `.pack_into(self, buffer, offset, *values) -> None`: Pack the values into an object supporting the
  [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html), at the given offset.
- `.pack_write(self, writable, *values) -> None`: Pack the values and write them to the file-like
  object `writable`.

#### Unpacking methods
- `.preunpack(self, partial_object) -> Serializer` (**not required**): This will be called just
  prior to any of the unpack methods of the `Serializer`, with a (maybe proxy of) the `Structured`
  object to be unpacked. This means the only attributes guaranteed to exist on the object are
  those that were serialized *before* those handled by this serializer. Again, in most cases the
  default implementation should work fine, which just returns itself unchanged.
- `.unpack(self, byteslike) -> Iterable`: Unpack from the bytes-like object, returning the values in
  an iterable. In most cases, just returning the values in a tuple should be fine. Iterables are
  supported so that the partial-proxy objects can have their attributes set more easily during
  unpacking.  Note: the number of values in the iterable must be `.num_values`. NOTE: unlike
  `struct.unpack`, the byteslike object is not required to be the *exact* length needed for
  unpacking, only *at least* as long as required.
- `.unpack_from(self, buffer, offset=0) -> Iterable`: Like `.unpack`, but from an object supporting
  the [Buffer Protocol](https://docs.python.org/3/c-api/buffer.html), at the given offset.
- `.unpack_read(self, readable) -> Iterable`: Like `.unpack`, but reading the data from the
  file-like object `readable`.

#### Other
- `.with_byte_order(self, byte_order: ByteOrder) -> Serializer)`: Return a (possibly new) serializer
  configured to use the `ByteOrder` specified.  The default implementation returns itself unchanged,
  but in most cases this should be overridden with a correct implementation.
- `.__add__(self, other) -> Serailzer` (**not required**): The final serializer used for a
 `Structured` class is determined by "adding" all of the individual serializers for each attribute
 together.  In most cases the default implementation will suffice.  You can provide your own
 implementation if optimizations can be made (for example, see `StructSerializer`'s implementation).


### The "building" Serializers
There are a few basic serializers used for building others:
- `NullSerializer`: This is a serializer that packs and unpacks nothing. This will be the serializer
  used by a `Structured` class if *no* serializable instance variables are detected. It is also used
  as the starting value to `sum(...)` when generating the final serializer for a `Structured` class.
- `CompoundSerializer`: This is a generic "chaining" serializer. Most serializers don't have an
  easy way to combine their logic, so `CompoundSerializer` handles the logic of calling the packing
  and unpacking methods one after another. This is a common serializer to see as the final
  serializer for a `Structured` class. This is also an interesting example to see how to handle
  variable `.size`, and handling `.preunpack` and `.prepack`.


### Specific Serializers
The rest of the Serializer classes are for handling specific serialization types.  They range from
very simple, to quite complex.

- `StructSerializer`: For packing/unpacking types which can be directly related to a constant
  `struct` format string.  For example, `uint32` is implemented as
  `Annotated[int, StructSerializer('I')]`.
- `StructActionSerializer`: This is the class used for `StructSerializer`-able custom types, but
  need to perform a custom callable on the result(s) to convert them to their final type.  It is
  almost identical to `StructSerializer`, but calls an `action` on each value unpacked.
- `TupleSerializer`: A fairly simple serializer that handles the `tuple` type-hints.
- `AUnion`: The base for both union serializers.
- `LookbackDecider`: The union serializer which allows for reading attributes already unpacked on
  the object to make a decision.
- `LookaheadDecider`: The union serializer which unpacks a little data then rewinds, using the
  unpacked value to make a decision.
- `StructuredSerializer`: A fairly simple serializer to handle translating the `Structured` class
  methods into the `Serializer` API.
- `DynamicCharSerializer`: The serializer used to handle `char[uint*]` type-hints.
- `TerminatedCharSerializer`: The serializer used to handle `char[b'\x00']` type-hints.
- `UnicodeSerializer`: A wrapper around one of the `char[]` serializers to handle encoding on
  packing and decoding on unpacking.


### Type detection
This is a very internal-level detail, but may be required if you write your own `Serializer` class.

Almost all of the typehints use `typing.Annotated` to specify the `Serializer` instance to use for
a hint. In most cases, it's as simple as creating your serializer, then defining a type using this.
See all of the "basic" types for example.  In some more complicated examples, which are configured
via the `__class_getitem__` method, these return `Annotated` objects with the correct serializer.

In any case, the `Structured` class detects the serializers by inspecting the `Annotated` objects
for serializers.  To support things like `a: Annotated[int, int8]`, it even recursively looks inside
nested `Annotated` objects. For most of this work, `structured` internally uses a singleton object
`structured.type_checking.annotated` to help extract this information. There is a step to perform
extra transformations on these `Annotated` extras, that a new `Serializer` you implement might need
to work.  Check out for example, `TupleSerializer` and `StructuredSerializer` on where that might
be necessary.
