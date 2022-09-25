Types
========

Structured provides quite a few types to annotate your class with.  Here's a
breakdown of them.


Basic Types
-----------
These are the types that could be directly replaces with just using Python's
struct module instead.  Each of these types map directly to a specific, static
format specifier.  In fact, if your class uses only these types, its serializer
will be a subclass of ``struct.Struct``.  All of these types are implemented
using ``typing.Annotated``, so type checkers will see them as their actual
unpacked type.

=============== =========== ================
structured type Python type Format specifier
=============== =========== ================
``bool8``       ``int``     '?'
``int8``        ``int``     'b'
``uint8``       ``int``     'B'
``int16``       ``int``     'h'
``uint16``      ``int``     'H'
``int32``       ``int``     'i'
``uint32``      ``int``     'I'
``int64``       ``int``     'q'
``uint64``      ``int``     'Q'
``float16``     ``float``   'e'
``float32``     ``float``   'f'
``float64``     ``float``   'd'
``char``        ``bytes``   's'
``char[int]``   ``bytes``   '{int}s'
``pascal``      ``bytes``   'p'
``pascal[int]`` ``bytes``   '{int}p'
``pad``         N/A         'x'
``pad[int]``    N/A         '{int}x'
=============== =========== ================

Note that ``pad`` refers to padding bytes.  These are skipped past when
when unpacking, and null bytes are written when packing.  The associated
attribute is never set when unpacking, and never accessed when packing. As such
they should be considered non-existing attributes.  It is recommended to name
these with a leading underscore (for example: ``_: pad[2]``) to indicate this.


Complex Types
-------------
For more involved packing and unpacking, a format string cannot be generated at
the time of writing your code, for example, unpacking a null-terminated string,
where the length is not known.  All of these types need a little more logic.
If you use any of this in your class, its serializer will no longer be a
subclass of ``struct.Struct``.  Additionally, because these require indexing to
specialize, they are not implemented using ``typing.Annotated``.  As a result,
you may run into type checker errors (see Type Checkers LINK).  These do
subclass from their unpacked types, so most operations will not cause issue with
type checkers.

.. class:: char

    The ``char`` type hint denotes a ``bytes`` instance.  To customize how the
    bytes are unpacked, you can specialize in a few ways.

    - ``char``: Using ``char`` without specializing results in just a single
      byte being unpacked.  This is a Basic Type.
    - ``char[10]``: Specializing with an integer specifies a static number of
      bytes.  This is a Basic Type.
    - ``char[uint8]``: Specializing with one of the unsigned integer Basic Types
      indicates that an integer holding the byte count should be unpacked,
      followed by that many bytes.
    - ``char[b'\0']``: Specializing with a single byte indicates a terminated
      byte array.  Bytes will be unpacked until the terminator is encountered,
      and the resulting object will be those bytes (not including the terminator).
      For packing, if the object doesn't include the terminator, a ``ValueError``
      will be raised.
    - ``null_char``: This is just a helpful alias for ``char[b'\0']``.

.. class:: unicode

    Similar to ``char``, with a few extra features.  The ``bytes`` are
    automatically decoded to a ``str`` when unpacked, and automatically encoded
    to ``bytes`` when packed.  To customize how the encoding and decoding occurs
    ``unicode`` takes an optional second specialization argument, which defaults
    to using the UTF-8 codec.

    - ``unicode``: A single byte will be unpacked and decoded.
    - ``unicode[10]``: Specializing with an integer specifies a static number of
      bytes to be unpacked and decoded.
    - ``unicode[uint16]``: Specializing with one of the unsigned integer Basic
      Types indicates that an integer holding the byte cound should be unpacked,
      followed by that many bytes, which are then decoded.
    - ``unicode[b'\0']``: Specializing with a single byte indicates a terminated
      string to be unpacked and decoded.
    - ``unicode[..., 'utf16']``: Passing a string as the second option to
      ``unicode`` configures which Python codec to use for encoding and
      decoding.  It must be one of the supported Python codecs (LINK), and
      defaults to ``'utf8'``.
    - ``unicode[..., encoder_decoder]``: If the built in codecs are not enough,
      you can implement a ``EncoderDecoder`` class to provide encoding and
      decoding methods.
    - ``null_unicode``: This is just a helpful alias for
      ``unicode[b'\0', 'utf8']``.

.. class:: array

    An array is a ``list`` of objects.  To type hint one, first you must
    specifiy an array ``Header`` (LINK) to customize its length and optional
    data size unpacking and checking.  The second argument for the ``array``
    specifies what data type is stored in the array.

    - ``array[Header[...], float32]``: An array can hold any Basic Type, except
      ``pad`` types.
    - ``array[Header[...], MyStructuredClass]``: An array can hold any
      ``Structured`` derived type.

.. class:: Header

    Array headers are used to specify array length, and optionally a data size
    for the array.

    - ``Header[10]``: Using an integer indicates an array containing a fixed
      number of elements.  The array length is checked on packing, and a
      ``ValueError`` is raised if the length is incorrect.
    - ``Header[uint16]``: Using any of the unsigned integer Basic Types
      indicates an array whose length is stored in an integer occuring just
      prior to the array.
    - ``Header[..., uint8]``: Using any of the unsigned integer Basic Types
      indicates an array with its size in bytes (not including the header)
      stored just prior to the array elements, but after the array length (if
      present).  When unpacking the array, the actual amount of bytes used is
      checked against this integer and a ``ValueError`` is raised if it does not
      match.

      .. note::
        Data size integers are only supported for arrays containing
        ``Structured`` objects.


