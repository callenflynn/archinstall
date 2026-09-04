.. _fork.cal_preset:

Cal's Preset
============

``Cal's Preset`` is the automated installation mode of this fork.  It
bypasses the granular desktop/display-manager/dotfile prompts while keeping
disk safety intact: the flow always asks for a locale, credentials and an
explicit target disk before anything is written.

Workflow

#. **Locale & mirrors** - pick a locale; the installer then auto-ranks the
   nearest Arch mirrors with ``reflector`` (best effort - on failure the
   standard Arch ISO mirrorlist is used unchanged).
#. **User credentials** - username and password.  The user is added to the
   ``wheel`` group with full sudo privileges
   (``%wheel ALL=(ALL:ALL) ALL``); the root password defaults to the same
   password.
#. **Disk selection** - a single 1-click target disk menu.  The preset then
   applies a best-effort partitioning layout with ``ext4`` and swap
   enabled (zram).
#. Everything below is hard-coded and applied automatically.

Hard-coded defaults

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Component
     - Preset default
   * - Desktop environment
     - Hyprland (wayland)
   * - Dotfiles suite
     - ``Ambxst`` (https://github.com/Axenide/Ambxst) - see :ref:`fork.dotfiles`
   * - Display manager
     - ``greetd`` + ``tuigreet`` (``greetd.service``) - see :ref:`fork.display_manager`
   * - Filesystem
     - ext4 best-effort layout, zram swap enabled
   * - Bootloader
     - ``systemd-boot``
   * - Audio
     - ``pipewire``
   * - AUR helper
     - ``paru`` (installed guarded, only when the configured repositories provide it)
   * - Repositories
     - CachyOS repositories enabled with automatic ISA-level detection - see :ref:`fork.cachyos`
   * - GPU drivers
     - automatic detection and driver selection - see :ref:`fork.hardware`
   * - User
     - ``wheel`` group member with full sudo; root password mirrors the user password

The whole run follows the :ref:`guided` installation pipeline, so logging,
rollback safety and error reporting behave like any other guided install.

Configuring the preset in the guided menu

The preset is remembered for the session: aborting/retrying from the
``GlobalMenu`` does not re-ask the entry question.  Everything the preset
collected is written into the regular configuration objects and can be
reviewed with ``archinstall --dry-run`` or by saving the configuration
inside the installer (``Save configuration``), exactly like upstream.
