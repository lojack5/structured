# Generating docs
This is just information gathered from various guides to remind myself how to
setup and build docs.

## Prereqs
Install sphinx:
`> pip install -U sphinx`

Install nicer theme:
`> pip install sphinx-rtd-theme`

And maybe(?) this one:
`> pip install sphinx_autodoc_typehints`


## Configuring
Run the sphinx quickstart (place docs source and builds in a subdirectory called `docs`):
`> sphinx-quickstart docs`

Edit `docs/source/conf.py`
1. Point to the correct location of the library (for autodocs):
   ```python
       import os
       import sys
       sys.path.insert(0, os.path.abspath('../..'))
   ```
2. Use autodoc:
   ```python
   extensions = ['sphinx.ext.autodoc', 'sphinix_autodoc_typehints']  # Maybe not the typhints one?
   ```
3. Use the nicer theme
   ```python
   html_theme = 'sphinx_rtd_theme'
   ```


## Build autodocs (need to run this any time new source files are added/removed/renamed)
`> sphinx-apidoc -o docs/source structured`


## Build docs
In the `source` directory:
`> make html`
`> make epub`


# Remaining TODOs:
- Deal with warnings/errors in docs build process (mostly just warnings)
- Edit source files for welcome messages, etc.
- Edit docstrings so they end up how we want them:
  - Naming
  - Private/internal APIs/methods
  - Typehints
- Upload to readthedocs.io
