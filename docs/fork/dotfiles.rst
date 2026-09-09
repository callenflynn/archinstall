.. _fork.dotfiles:

Secured dotfile deployment
==========================

Hyprland users can have a third-party dotfiles/ricing suite deployed
automatically. Third-party repositories are treated as **untrusted input**
throughout.

Available suites (Custom Setup prompt)
--------------------------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Suite
     - Repository
   * - Ambxst *(Recommended)*
     - https://github.com/Axenide/Ambxst
   * - Caelestia
     - https://github.com/caelestia-dots/caelestia
   * - end-4
     - https://github.com/end-4/dots-hyprland
   * - ML4W
     - https://github.com/mylinuxforwork/dotfiles (https://ml4w.com)
   * - None / Vanilla
     - no dotfiles are deployed

The **ML4W** suite is deployed differently: it ships no top-level installer,
so the fork copies its ``dotfiles/`` configuration subfolder into ``$HOME``
(matching the suite's own ``.dotinst`` profile), stages its repository
dependency lists through pacman, and then runs its ``setup/preflight-arch.sh``
and ``setup/post-arch.sh`` with ``$repo_path`` exported.  Because these
scripts call ``sudo`` internally, a *temporary* passwordless sudo grant is
installed for the target user and revoked in a ``finally`` block once the
deployment finishes; stdin is closed so interactive prompts cannot hang a
non-interactive install.  AUR-only packages (quickshell, matugen, awww, ...)
are installed by the scripts themselves via ``paru``.

Cal's Preset always deploys ``Ambxst``. The Hyprland dotfiles prompt only
appears in the Custom Setup flow when Hyprland was chosen; other desktop
environments skip it, and **Minimal CLI** bypasses the DE/DM/dotfile prompts
entirely.

Deployment steps (inside the target chroot)
-------------------------------------------

#. **Clone as the user** - the repository is cloned directly into
   ``/home/<username>/<suite>`` *as the target user* (never as root), so
   every file already carries the correct ownership.
#. **Inspection** - the freshly cloned repository's installer scripts
   (``setup.sh`` / ``install.sh`` / ``install.fish`` / ``setup``) and
   README are *read, never executed*. If the project manages its own
   dependencies (its scripts invoke a package manager), nothing is added;
   otherwise the conservative prerequisite set (``git``, ``kitty``,
   ``waybar``, ``rofi-wayland``) is appended to the pacman transaction
   before running the scripts.
#. **Drop-privileged execution** - installer scripts run strictly as the
   target user via ``su - <username> -c <command>``. Scripts are never
   piped from remote sources (``curl | sh`` is not used) and never run as
   root.  (The ML4W suite is the sole exception that receives a temporary,
   auto-revoked passwordless-sudo grant, because its scripts call ``sudo``
   internally; see above.)
#. **Ownership repair** - ``chown -R <username>:<username> /home/<username>/``
   is applied on success and failure so the user's home directory is
   always usable.

Failure handling
----------------

Clone, dependency or script failures are logged with a warning, ownership
is repaired, and the installation continues with a **vanilla (un-dotted)
Hyprland** desktop - dotfiles are never allowed to abort an installation.
