Tutorial
========

.. module:: structured


Welcome to the Structured tutorial.  Structured is a small library for dealing
with data structures that map to C structures.  Under the hood it uses Python's
struct module, but it handles a lot of common patterns for you.  Additionally,
it leverages type hints to make defining your classes quick and easy.

Before you begin
----------------
1. Make sure you're on Python 3.9+
2. Install via pip ``pip install structured-classes``.
3. Now just ``import structured`` and you should be good to go.

A simple example
----------------
For this example, we'll look at The Elder Scrolls IV: Oblivion.  It's data files
can get pretty complex, but for this we'll just tackle reading and writing the
shaders packaged with the game.  These shaders come packed in shader package
(.sdp) files, and their format is pretty simple.  All integers are stored in
little endian byte order.

1. 4 bytes - a file type indicator, always 0x64 0x00 0x00 0x00.
2. 4 bytes - integer holding the number of shaders in the package.
3. 4 bytes - integer holding the total size of the shaders themselves

Followed by the shaders.  Each shader holds the following data.

1. 0x100 bytes - The name of the shader.  We're not sure what encoding it's stored
in, so we'll try UTF-8 for now.
2. 4 bytes - integer holding the size of the shader data
3. A chunk of bytes (size determined in 2).  This is the raw data of the shader
file.


So lets quickly whip this up into classes that can pack and unpack this::

   from structured import Structured, ByteOrder, uint32, unicode, char
   from typing import ClassVar

   class Shader(Structured, byte_order=ByteOrder.LE):
       __slots__ = ('name', 'shader_data', )

       # These attributes get handled by structured
       name: unicode[0x100]
       shader_data: char[uint32]

   class ShaderPackage(Structured, byte_order=ByteOrder.LE):
       __slots__ = ('_magic', 'shaders', )
       MAGIC: ClassVar[int] = 0x64

       # These attributes get handled by structured
       _magic: uint32
       shaders: array[Header[uint32, uint32], Shader]

Lets pick apart this example a little.  First, notice we subclass from
``Structured``. This gets the automatic detection of attributes going.  Any
attribute annotated as a non-``ClassVar`` and one of structured's provided types
end up in the final pack/unpack behaviour for this class.

We also passed ``byte_order=ByteOrder.LE`` to the class's subclass machinery, to
indicate that integers should be unpacked using the little endian byte order
format.

For the shaders themselves, we indicated that 256 bytes of data should be read
as a string, and decoded using the UTF-8 codec (this is the default, since we
did not provide an encoding option) by hinting with ``unicode[0x100]``. Next, we
indicated that a 4 byte unsigned integer will be followed by that many bytes of
data by hinting with ``char[uint32]``.

Finally, we grouped this into the shader package itself.  It starts with 4
bytes, which we'll unpack as an unsigned integer (``uint32``).  We could check
that it matches the ClassVar ``MAGIC`` if we wanted to, but we've skipped this
for now. Following that is a list of shaders.  We want to tell Structured that
the list starts with a 4 byte integer determining how many shaders, then a 4
byte integer determining the total size of the list, so we hinted with
``array[Header[uint32, uint32], Shader]``.  The ``Header`` gives ``array``
information about how many shaders to unpack (the first argument) and that it
has a data size integer (the second argument).  After the header, we tell
``array`` to unpack those objects using the ``Shader`` class we just defined.

Now we can load or edit these shader packages with these classes.  For example,
say we want to extract shaders from a shader package::

   def extract_shader_package(filename: os.PathLike, output_directory: Path):
       # Read the shader package
       with open(filename, 'rb') as ins:
           sdp = ShaderPackage.create_unpack_read(ins)
       # Save its contents to the output directory
       for shader in sdp.shaders:
           outname = output_directory.joinpath(shader.name)
           with open(outname, 'wb') as out:
               out.write(shader.shader_data)

And that's it!  For more reading, you can check out:
- Comparison to struct (TODO)
- Basic types (TODO)
- Advanced types (TODO)
- How it works (TODO)
