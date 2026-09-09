"""
Opinionated setup modes and their option vocabulary.

This package implements the "Cal's Preset vs. Custom Setup" fork flow on top of
archinstall's configuration model.  This module only contains plain data /
enumeration types so that pure logic (and tests) never need a TUI or a running
installation.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from archinstall.default_profiles.profile import GreeterType


class SetupMode(StrEnum):
	PRESET = 'cal_preset'
	CUSTOM = 'custom_setup'

	def display_name(self) -> str:
		match self:
			case SetupMode.PRESET:
				return "Cal's Preset (Recommended - Fast setup with Hyprland + Ambxst)"
			case SetupMode.CUSTOM:
				return 'Custom Setup (Granular step-by-step configuration)'


class CachyosLevel(StrEnum):
	"""CachyOS ISA repository levels."""

	GENERIC = 'generic'
	V3 = 'v3'
	V4 = 'v4'
	ZNVER4 = 'znver4'


class Desktop(StrEnum):
	"""
	The desktop environments offered by the fork's DE selection menu.

	Values intentionally match the archinstall profile names so a choice can be
	resolved back to a :class:`~archinstall.default_profiles.profile.Profile`.
	"""

	KDE_PLASMA = 'KDE Plasma'
	HYPRLAND = 'Hyprland'
	GNOME = 'GNOME'
	CINNAMON = 'Cinnamon'
	XFCE = 'XFCE'
	MINIMAL_CLI = 'Minimal CLI'

	def recommended(self) -> bool:
		return self in (Desktop.KDE_PLASMA, Desktop.HYPRLAND)

	def is_desktop_env(self) -> bool:
		return self != Desktop.MINIMAL_CLI


class Dotfiles(StrEnum):
	"""
	Curated Hyprland dotfile suites.

	The repository URL is embedded so the installer never has to fetch
	metadata from the network to decide *what* to clone.  The actual clone is
	treated as untrusted input at deployment time (see
	:mod:`archinstall.preset.dotfiles`).
	"""

	AMBXST = 'Ambxst'
	CAELESTIA = 'Caelestia'
	END4 = 'end-4'
	ML4W = 'ML4W'

	@property
	def repository(self) -> str:
		match self:
			case Dotfiles.AMBXST:
				return 'https://github.com/Axenide/Ambxst'
			case Dotfiles.CAELESTIA:
				return 'https://github.com/caelestia-dots/caelestia'
			case Dotfiles.END4:
				return 'https://github.com/end-4/dots-hyprland'
			case Dotfiles.ML4W:
				return 'https://github.com/mylinuxforwork/dotfiles'

	def display_name(self) -> str:
		match self:
			case Dotfiles.AMBXST:
				return 'Ambxst (Recommended)'
			case _:
				return self.value


class GpuPlan(StrEnum):
	"""Resolved GPU driver strategy; ``GENERIC_MESA`` is the always-safe fallback."""

	GENERIC_MESA = 'mesa (fallback)'
	AMD = 'AMD (open source)'
	INTEL = 'Intel (open source)'
	NVIDIA_OPEN = 'NVIDIA (open kernel module, Turing+)'
	NVIDIA_LEGACY = 'NVIDIA (nouveau, pre-Turing fallback)'
	HYBRID = 'Hybrid / dual GPU'
	VM = 'Virtual machine'


@dataclass
class PresetOptions:
	"""
	Runtime options that drive the fork's installation extensions.

	These values are intentionally *not* part of the archinstall config schema;
	they are carried alongside :class:`~archinstall.lib.args.ArchConfig` (plain
	dataclass attribute) and consumed by the guided install flow.

	``cachyos`` is ``None`` when the user opted out (vanilla Arch repositories).
	The generic level is stored as :class:`CachyosLevel.GENERIC`; detection
	upgrades it to ``v3``/``v4``/``znver4`` when unambiguous.  ``None`` means the
	user opted out of CachyOS repositories entirely.
	"""

	mode: SetupMode
	desktop: Desktop = Desktop.HYPRLAND
	dotfiles: Dotfiles | None = Dotfiles.AMBXST
	greeter: GreeterType | None = None
	cachyos: CachyosLevel | None = CachyosLevel.GENERIC
	detected_gpu_plan: GpuPlan | None = None
	detected_gpu_packages: list[str] = field(default_factory=list)
	extra_packages: list[str] = field(default_factory=list)
	deploy_dotfiles: bool = True
	use_paru: bool = True

	@classmethod
	def cal_preset(cls) -> PresetOptions:
		"""The hard-coded 'Cal's Preset' option set (MODE A)."""
		return cls(
			mode=SetupMode.PRESET,
			desktop=Desktop.HYPRLAND,
			dotfiles=Dotfiles.AMBXST,
			greeter=GreeterType.GreetdTuigreet,
		)

	def summary(self) -> list[str]:
		out = [f'Mode: {self.mode.display_name()}']
		out.append(f'Desktop: {self.desktop.value}')

		if self.desktop.is_desktop_env():
			if self.greeter is not None:
				out.append(f'Greeter: {self.greeter.value}')

			if self.dotfiles is not None:
				out.append(f'Dotfiles: {self.dotfiles.value}')
			else:
				out.append('Dotfiles: None / vanilla')

		if self.cachyos:
			out.append(f'CachyOS repositories: {self.cachyos}')

		if self.detected_gpu_plan:
			out.append(f'GPU driver plan: {self.detected_gpu_plan.value}')

		return out
