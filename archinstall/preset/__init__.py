"""
Fork package: "Cal's Preset vs. Custom Setup" installation flows.

Modules:

* :mod:`options`        - modes / DE / dotfile / repository vocabulary
* :mod:`detect`         - GPU detection + driver package planning
* :mod:`cachyos`        - CachyOS repository + CPU ISA integration
* :mod:`display_manager`- dynamic DM recommendation + greetd deployment
* :mod:`dotfiles`       - secured (drop-privileged) dotfile deployment
* :mod:`mirrors`        - best-effort reflector auto-ranking
* :mod:`builder`        - pure config assembly on the archinstall models
* :mod:`wizard`         - TUI prompts (single location that touches menus)
* :mod:`flow`           - entry + preset/custom orchestration
* :mod:`runtime`        - install-time hooks consumed by the guided script
"""

from archinstall.preset.options import CachyosLevel, Desktop, Dotfiles, PresetOptions, SetupMode

__all__ = [
	'CachyosLevel',
	'Desktop',
	'Dotfiles',
	'PresetOptions',
	'SetupMode',
]
