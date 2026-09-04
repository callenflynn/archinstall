"""
Runtime extension hooks executed from the guided installation loop.

The fork keeps archinstall's stock flow; these hooks are invoked at fixed
points of ``guided.perform_installation`` when an :class:`PresetOptions` is
attached to the config:

* :func:`prepare_repositories` - live-medium CachyOS repo enablement, *before*
the base pacstrap;
* :func:`synchronize_system` - full ``pacman -Syu`` in the target chroot (after
base, before swap/bootloader);
* :func:`apply_finalize` - greeter config/session, GPU initramfs regeneration,
dotfile deployment, paru and the *final* keyring trust pass (after profile
install and service enablement, before genfstab).
"""

from typing import TYPE_CHECKING

from archinstall.default_profiles.profile import GreeterType
from archinstall.lib.log import debug, info
from archinstall.preset import cachyos
from archinstall.preset.builder import desktop_from_profile
from archinstall.preset.display_manager import deploy_greetd
from archinstall.preset.dotfiles import deploy as deploy_dotfiles
from archinstall.preset.options import Desktop, GpuPlan, PresetOptions

if TYPE_CHECKING:
	from archinstall.lib.args import ArchConfig
	from archinstall.lib.installer import Installer
	from archinstall.lib.models.users import User


def prepare_repositories(config: ArchConfig) -> None:
	"""Enable CachyOS repositories on the live medium before the base strap."""
	if not (preset := config.preset) or not preset.cachyos:
		return

	cachyos.prepare_live_environment(preset.cachyos)


def base_extra_packages(config: ArchConfig) -> list[str] | None:
	"""
	Packages that must ride the *same* base pacstrap transaction as the base
	system: the CachyOS keyring + mirrorlist packages.
	"""
	if not (preset := config.preset) or not preset.cachyos:
		return None

	return cachyos.mirrorlist_packages_for_level(preset.cachyos)


def synchronize_system(config: ArchConfig, installation: Installer) -> None:
	"""Full synchronized upgrade + initramfs regeneration in the target chroot."""
	if not (preset := config.preset) or not preset.cachyos:
		return

	cachyos.synchronize_target(installation, preset.cachyos)


def _needs_initramfs_rebuild(preset: PresetOptions) -> bool:
	if preset.detected_gpu_plan in (GpuPlan.NVIDIA_OPEN, GpuPlan.HYBRID):
		return True

	return any('nvidia' in pkg for pkg in preset.detected_gpu_packages)


def apply_finalize(
	config: ArchConfig,
	installation: Installer,
	users: list[User] | None,
) -> None:
	"""
	Desktop/dotfile/GPU/keyring finalization.

	Failures here follow the fork resilience spec: dotfile + paru + initramfs
	steps warn and continue; the CachyOS keyring trust restore is critical.
	"""
	preset = config.preset
	if preset is None:
		return

	# The *actual* profile configuration (the user may have changed the DE in
	# the custom GlobalMenu after the wizard ran) is the source of truth for
	# the greeter and the session executable.
	profile_config = config.profile_config
	desktop = desktop_from_profile(profile_config)
	greeter = profile_config.greeter if profile_config and profile_config.greeter else preset.greeter

	# --- display manager -------------------------------------------------
	if greeter == GreeterType.GreetdTuigreet and desktop is not None and desktop.is_desktop_env():
		deploy_greetd(installation, desktop)
	elif desktop is not None and desktop.is_desktop_env() and greeter is not None:
		info(f'Display manager handled by the profile layer (greeter: {greeter.value})')

	# --- GPU: initramfs regeneration after proprietary driver install -----
	if _needs_initramfs_rebuild(preset):
		debug('Regenerating initramfs after GPU driver installation')
		try:
			installation.arch_chroot('mkinitcpio -P', peek_output=True)
		except Exception as err:
			from archinstall.lib.log import warn

			warn(f'initramfs regeneration after GPU driver installation failed: {err}')

	# --- dotfiles (Hyprland-only by design) --------------------------------
	if desktop != Desktop.HYPRLAND:
		debug('Dotfile deployment skipped: only relevant for Hyprland')
	elif preset.dotfiles is not None and users:
		target_user = users[0]
		deploy_dotfiles(installation, preset.dotfiles, target_user.username)
	elif preset.dotfiles is not None:
		from archinstall.lib.log import warn

		warn('Dotfile deployment skipped: no regular user was configured')

	# --- AUR helper (guarded, optional) -----------------------------------
	if preset.use_paru:
		cachyos.install_paru_guarded(installation)

	# --- keyring trust (must be the very last pacman/gnupg operation) -----
	if preset.cachyos:
		cachyos.ensure_target_keyring_trust(installation)
