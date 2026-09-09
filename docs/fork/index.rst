.. _fork:

Fork: Preset vs. Custom setup
=============================

This fork keeps the full upstream :ref:`guided` installer intact and adds a
top-level **entry screen** that appears the moment the guided installer is
launched (interactive runs only):

* **Cal's Preset** *(Recommended - Fast setup with Hyprland + Ambxst)*
  A fully automated, opinionated installation. Only four questions are
  asked (locale, username + password, target disk); everything else is
  derived from the preset's defaults documented in :ref:`fork.cal_preset`.
* **Custom Setup** *(Pick your own options, same linear flow)*
  The identical step-by-step prompt sequence, but every answer is the
  user's: CachyOS repositories, desktop environment (KDE Plasma /
  Hyprland recommended), Hyprland dotfiles (Ambxst / Caelestia / end-4 /
  ML4W), display manager with a dynamic recommendation, credentials and
  target disk.

Both modes are **strictly linear**: no nested menu, every question appears
once, in order, and aborting the final confirmation re-runs the same
sequence with all previous answers pre-filled for quick revision.  The
classic granular ``GlobalMenu`` remains available via ``--advanced``.

Both modes feed the **same** ``ArchConfig``/``ProfileConfiguration`` model
that upstream's ``GlobalMenu`` edits, so saved configurations, declarative
``--config`` runs and the guided installation loop behave exactly like
upstream - the fork only pre-fills the answers.

Highlights of the fork
----------------------

* :ref:`fork.cal_preset` - hard-coded defaults of the automated preset.
* :ref:`fork.cachyos` - CachyOS repositories as primary package providers,
  CPU ISA-level detection and keyring handling.
* :ref:`fork.hardware` - live GPU detection and dynamic driver selection
  (NVIDIA Turing+ / AMD / Intel / hybrid).
* :ref:`fork.display_manager` - desktop-dependent display manager
  recommendations and the ``greetd + tuigreet`` deployment.
* :ref:`fork.dotfiles` - secured, drop-privileged dotfile deployment.

Failure handling follows a strict policy (see :ref:`fork.cachyos` and
:ref:`fork.dotfiles`): critical steps (GPG key import, base packages, user
creation, partitioning) abort with a clear error; optional steps (mirror
ranking, GPU detection, dotfiles) log a warning, fall back safely and
continue.

.. toctree::
   :maxdepth: 1
   :caption: Fork guide

   cal_preset
   cachyos
   hardware
   display_manager
   dotfiles
