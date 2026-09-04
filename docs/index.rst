archinstall Documentation
=========================

**archinstall** is a library which can be used to install Arch Linux.
The library comes packaged with different pre-configured installers, such as the default :ref:`guided` installer.

This fork adds a **Preset vs. Custom** installation workflow on top of the guided installer: a fully automated *Cal's Preset* (Hyprland + Ambxst dotfiles, CachyOS repositories, automatic GPU driver selection, ``greetd + tuigreet``) and the classic granular flow with opinionated defaults.  See :ref:`fork` for the full guide.

Some of the features of Archinstall are:

* **Context friendly.** The library always executes calls in sequential order to ensure installation-steps don't overlap or execute in the wrong order. It also supports *(and uses)* context wrappers to ensure cleanup and final tasks such as ``mkinitcpio`` are called when needed.

* **Full transparency** Logs and insights can be found at ``/var/log/archinstall`` both in the live ISO and partially on the installed system.

* **Accessibility friendly** Archinstall works with ``espeakup`` and other accessibility tools thanks to the use of a TUI.

.. toctree::
   :maxdepth: 1
   :caption: Fork guide

   fork/index

.. toctree::
   :maxdepth: 1
   :caption: Running Archinstall

   installing/guided

.. toctree::
   :maxdepth: 3
   :caption: Getting help

   help/known_issues
   help/report_bug
   help/discord

.. toctree::
   :maxdepth: 3
   :caption: Archinstall as a library

   installing/python
   examples/python
   archinstall/plugins

.. toctree::
   :maxdepth: 3
   :caption: API Reference

   archinstall/Installer
