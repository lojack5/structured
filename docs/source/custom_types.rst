Custom Types
============

If the built in data types are not enough for you, there are a few tools for
making your own.  The easiest if to use ``Formatted``, which will result in a
type that can be used any place a Basic Type could be used.  The second is for
when more complex logic is needed, a ``Serializer``.

Formatted
---------
When you just need to wrap a Basic Type with some additional features, but no
additional packing or unpacking logic, you should base your class on
``Formatted``.  Your class will be a thin wrapper around a Basic Type.  An
example of this is to wrap an integer that represents a boolean flag field with
additional functionality to access or set those fields.

The default behaviour of the ``Formatted`` base class is to allow specialization
of your class with one of the Basic Types.  The specialized version of your
class will then pack and unpack using that Basic Type's format specifier.

.. note::
    If your type encapsulates an ``int``, make sure it provides an ``__index__``
    method or it will not be able to be packed.

.. note::
    If your type encapsulates a ``float``, make sure it provides a ``__float__``
    method or it will not be able to be packed.

Unfortunately, if your type encapsulates a ``bytes`` object, you will have to
actually make your type a subclass of ``bytes`` and be immutable.  This is due
to ``struct`` not calling ``__bytes__`` when using any of the string format
specifiers.  If this will not work for you (like it does not for most of the
provided string types), you will need a custom ``Serializer`` for your type.

If you don't want the default behaviour of allowing your class to be specialized
as any Basic Type, you can narrow which types are allowed by setting the class
variable ``_types`` to a container with the allowed Basic Types.

Finally, the default behaviour when unpacking is to call your class's
``__init__`` with the unpacked value as a single argument.  If your class cannot
support this, set the class variable ``unpack_action`` to a callable taking this
single value, and returning an instance of your class.

As an example, here is a basic boolean field class.  As a boolean field, it
makes the most sense to only allow unsigned integers::

    class BooleanField(Formatted):
        # Only allow unsigned integers
        _types = {uint8, uint16, uint32, uint64}

        value: int

        def __init__(self, value: int) -> None:
            self.value = value

        def get_field(self, index: int) -> bool:
            return bool(self.value & 1 << index)

        def set_field(self, index: int, value: bool = True) -> None:
            mask = ~(1 << index)
            bit = value << index
            self.value &= (bit | mask)

        def __index__(self) -> int:
            """For struct.pack"""
            return self.value

        # Bitwise operations
        def __not__(self) -> BooleanField:
            return type(self)(~self.value)

        def __and__(self, other: BooleanField | int) -> BooleanField:
            if (rtype := type(self)) is type(other):
                return rtype(self.value & other.value)
            elif isinstance(other, int):
                return rtype(self.value & other)
            return NotImplemented

        def __or__(self, other: BooleanField | int) -> BooleanField:
            if (rtype := type(self)) is type(other):
                return rtype(self.value | other.value)
            elif isinstance(other, int):
                return rtype(self.value | other)
            return NotImplemented

        def __xor__(self, other: BooleanField | int) -> BooleanField:
            if (rtype := type(self)) is type(other):
                return rtype(self.value ^ other.value)
            elif isinstance(other, int):
                return rtype(self.value ^ other)
            return NotImplemented

You could then use this as a type hint for one of your ``Structured`` classes::

    class MyData(Structured):
        flags: BooleanField[uint8]
        data: char[uint32]

.. note::
    If you do not specialize your ``Formatted`` class, it will not be detected
    as an attribute to be packed or unpacked!


Serializers
-----------

When the provided types and even ``Formatted`` isn't enough, it's time to write
your own ``Serializer``.  Serializers provide all of the packing and unpacking
logic for a data type, and function almost like a ``struct.Struct`` instance.

.. note::
    If you think your use case for a ``Serializer`` is common, feel free to open
    a feature request (LINK)!

.. currentmodule:: structured
.. autoclass:: Serializer
   :members:
   :undoc-members:
   :special-members: __init__

For some examples on how to actually implement this, take a look at the source
files in :mod:`structured.complex_types`.  Note if you are creating a
Serializer for a container type and wish to support generics, check out the
section on coding for that as well (TODO: LINK).
