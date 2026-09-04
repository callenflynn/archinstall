.. _fork.cachyos:

CachyOS repository integration
==============================

The fork can use the `CachyOS repositories <https://cachyos.org/>`_ as the
primary package providers.  Repository facts used below were verified
against the official `CachyOS repository installer <https://github.com/CachyOS/cachyos-repo-add-script>`_
and the `Optimized Repositories wiki page <https://wiki.cachyos.org/features/optimized_repos/>`_.

CPU ISA level detection
-----------------------

Before the repositories are enabled, the host CPU's x86-64 microarchitecture
level is detected:

* ``glibc`` supported levels are read from ``/lib/ld-linux-x86-64.so.2 --help``
  (``x86-64-v3`` / ``x86-64-v4``).
* When ``gcc`` is available, ``-march=native`` is consulted so AMD
  ``znver4``/``znver5`` systems resolve to the ``znver4`` repositories.

Resolution rules:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Detection result
     - Repository level used
   * - ``x86-64-v3``
     - ``[cachyos-v3]`` / ``[cachyos-core-v3]`` / ``[cachyos-extra-v3]``
   * - ``x86-64-v4`` (non-AMD, gcc-confirmed or glibc-only)
     - ``[cachyos-v4]`` / ``[cachyos-core-v4]`` / ``[cachyos-extra-v4]``
   * - AMD Zen4+ (positive ``gcc -march=native`` signal)
     - ``[cachyos-znver4]`` family (shares the ``cachyos-v4-mirrorlist``)
   * - Ambiguous / ``v1`` / ``v2`` / detection failed
     - plain ``[cachyos]`` (generic, no ISA suffix)

``pacman.conf`` injection
-------------------------

The generated stanzas are inserted at the **very top** of the target's
``/etc/pacman.conf``, *above* ``[core]`` and ``[extra]`` so CachyOS becomes
the primary provider.  The operation is idempotent: an existing ``[cachyos]``
section is left untouched.

.. code-block:: ini

   [cachyos-v3]
   Include = /etc/pacman.d/cachyos-v3-mirrorlist
   [cachyos-core-v3]
   Include = /etc/pacman.d/cachyos-v3-mirrorlist
   [cachyos-extra-v3]
   Include = /etc/pacman.d/cachyos-v3-mirrorlist
   [cachyos]
   Include = /etc/pacman.d/cachyos-mirrorlist

   [core]
   Include = /etc/pacman.d/mirrorlist
   [extra]
   Include = /etc/pacman.d/mirrorlist

Runtime sequence
----------------

#. **Live environment** - the CachyOS master key ``F3B607488DB35A47`` is
   imported and locally signed (``pacman-key --recv-keys`` +
   ``pacman-key --lsign-key``), and the live ``/etc/pacman.conf`` plus the
   mirrorlist files are written before the base pacstrap runs.
#. **Base transaction** - ``cachyos-keyring`` and the matching mirrorlist
   package (``cachyos-v3-mirrorlist`` / ``cachyos-v4-mirrorlist``) ride the
   *same* pacstrap transaction as the base system.
#. **Synchronized upgrade** - a full ``pacman -Syu --noconfirm`` runs inside
   the target chroot (never a partial ``pacman -Sy``), followed by an
   ``mkinitcpio -P`` initramfs regeneration.
#. **Keyring trust restore** - because every pacstrap re-initializes the
   chroot keyring, trust is re-established *after the last package
   transaction* with ``pacman-key --populate cachyos archlinux`` (offline);
   a keyserver import + local sign is the fallback.
#. **AUR helper** - when enabled, ``paru`` is installed from the configured
   repositories; failure to install it only logs a warning.

Failure handling
----------------

* **Critical** (installation aborts with a clear error): GPG key import
  failure, base package installation failure, user creation errors, disk
  partitioning failures.
* **Non-critical** (warning + safe fallback, installation continues):
  reflector failure (standard mirrorlist), GPU detection failure (generic
  open-source ``mesa``), CPU ISA ambiguity (generic ``[cachyos]``), dotfile
  failures (vanilla Hyprland), ``paru`` unavailability.
