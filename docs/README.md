# Documentation

This documentation site is built with [Sphinx](https://www.sphinx-doc.org/) from
the reStructuredText (`.rst`) sources in this directory. The rendered site is
deployed to GitHub Pages by `.github/workflows/deploy-docs.yml`.

## Structure

* `index.rst` - landing page and table of contents.
* `fork/` - **this fork's guide**: the Preset vs. Custom workflow
  (`index.rst`), Cal's Preset defaults (`cal_preset.rst`), CachyOS repository
  integration (`cachyos.rst`), GPU detection and driver selection
  (`hardware.rst`), display manager recommendations and the greetd+tuigreet
  deployment (`display_manager.rst`), and secured dotfile deployment
  (`dotfiles.rst`).
* `installing/` - running the guided installer and using archinstall as a
  Python library.
* `archinstall/`, `cli_parameters/`, `examples/`, `help/` - API reference,
  CLI/config reference, examples and known issues.

## Dependencies

In order to build the docs locally, you need to have the following installed:

- [sphinx](https://www.sphinx-doc.org/en/master/usage/installation.html)
- [sphinx-rtd-theme](https://pypi.org/project/sphinx-rtd-theme/)

For example, you may install these dependencies using pip:

```
pip install -U sphinx sphinx-rtd-theme
```

## Build

In `archinstall/docs`, run `make html` (or specify another target) to build
locally. The build files will be in `archinstall/docs/_build`. Open
`_build/html/index.html` with your browser to see your changes in action.

To validate reStructuredText and links before pushing, build with warnings
as errors:

```
sphinx-build -W -b html docs _build
```
