---
name: Prepare a Release
about: For developers, to aid in preparing a new release.
title: "[RELEASE]: "
---

A checklist of things that need to be done for a release:
- [ ] Create a release branch `release-<version>`
- [ ] Update documentation if needed
- [ ] Update the version string in `structured/__init__.py`
- [ ] Check for any needed updates from dependencies and update:
  - [ ] `pyproject.toml`
  - [ ] `requirements.txt`
  - [ ] `requirements-tests.txt`
- [ ] Update PyPi information in `pyproject.toml` with other needed changes (ex: supported Python versions)
- [ ] Create a Pull Request for all of these updates.
  - [ ] Verify all tests pass.
  - [ ] Merge the changes into `main`.
- [ ] [Create the distributables](https://packaging.python.org/en/latest/tutorials/packaging-projects/#generating-distribution-archives): `py -m build`
- [ ] [Upload the distributables to PyPi](https://packaging.python.org/en/latest/tutorials/packaging-projects/#uploading-the-distribution-archives) `py -m twine upload`
- [ ] Create a release on Github from the head of `main`.
- [ ] Close this issue.
