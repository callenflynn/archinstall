.. _fork.display_manager:

Display manager selection
=========================

The Custom Setup flow recommends (and pre-selects) a display manager based
on the desktop environment that was chosen:

.. list-table::
   :widths: 30 40 30
   :header-rows: 1

   * - Desktop environment
     - Recommended display manager
     - Greeter flag shown
   * - Hyprland
     - ``greetd`` + ``tuigreet``
     - Recommended for Hyprland
   * - KDE Plasma
     - ``sddm``
     - Recommended for KDE Plasma
   * - GNOME
     - ``gdm``
     - Recommended for GNOME
   * - Cinnamon / XFCE
     - ``lightdm``
     - Recommended
   * - Minimal CLI
     - none (no display manager prompt)
     - -

In **Cal's Preset** the display manager is hard-coded to
``greetd + tuigreet`` (``greetd.service``) and the prompt is skipped.

greetd + tuigreet deployment
----------------------------

When ``greetd + tuigreet`` is selected, the deployment step inside the
target chroot:

#. Maps the chosen DE/WM to a validated session executable by checking
   ``/usr/share/wayland-sessions/`` and ``/usr/share/xsessions/``
   (e.g. ``Hyprland``, ``startplasma-wayland``, ``gnome-session``); the
   first configured candidate is used as a fallback when nothing can be
   validated.
#. Writes ``/etc/greetd/config.toml``:

   .. code-block:: toml

      [terminal]
      vt = 1

      [default_session]
      command = "tuigreet --time --asterisks --user-menu --cmd <session>"
      user = "greeter"

#. Ensures the ``greeter`` system user exists, creates
   ``/var/cache/tuigreet`` with ``0755`` permissions owned by
   ``greeter:greeter`` (via a tmpfiles fragment and an idempotent user
   check).
#. Enables ``greetd.service``, disables ``getty@tty1`` and any conflicting
   display manager services (``sddm``, ``gdm``, ``lightdm``, ``ly``,
   ``cosmic-greeter``, ``plasmalogin``) so exactly one login manager owns
   the display.

Conflicting service disable steps are best-effort: a failure to disable one
only logs a debug message.
