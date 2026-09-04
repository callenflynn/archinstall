"""
Opinionated configuration assembly (pure logic on top of the archinstall
models, reused by the interactive flows and covered by unit tests).

Nothing in this module launches menus or runs commands; it translates user
choices (DE, dotfiles, greeter, defaults) into the archinstall configuration
vocabulary so the fork stays compatible with archinstall's config schema and
install flow.
"""

from archinstall.default_profiles.minimal import MinimalProfile
from archinstall.default_profiles.profile import CustomSetting, GreeterType
from archinstall.lib.args import ArchConfig
from archinstall.lib.hardware import GfxDriver
from archinstall.lib.models.application import ApplicationConfiguration, Audio, AudioConfiguration, ZramConfiguration
from archinstall.lib.models.authentication import AuthenticationConfiguration
from archinstall.lib.models.bootloader import BootloaderConfiguration
from archinstall.lib.models.device import DiskLayoutConfiguration
from archinstall.lib.models.locale import LocaleConfiguration
from archinstall.lib.models.mirrors import MirrorConfiguration
from archinstall.lib.models.pacman import PacmanConfiguration
from archinstall.lib.models.profile import ProfileConfiguration
from archinstall.lib.models.users import Password, User
from archinstall.lib.profile.profiles_handler import profile_handler
from archinstall.preset.display_manager import recommended_greeter
from archinstall.preset.options import Desktop, PresetOptions, SetupMode


def profile_config_for_desktop(
	desktop: Desktop,
	greeter: GreeterType | None = None,
	gfx_driver: GfxDriver | None = None,
) -> ProfileConfiguration:
	"""Build a :class:`ProfileConfiguration` for a desktop choice.

	Desktop environments map onto archinstall's ``Desktop`` top-level profile
	with the specific environment attached as a sub profile.  ``Minimal CLI``
	maps onto the ``Minimal`` profile - no DE, no greeter, no dotfiles: the
	DE/DM prompts are bypassed by construction.
	"""
	if desktop == Desktop.MINIMAL_CLI:
		return ProfileConfiguration(profile=MinimalProfile())

	if greeter is None:
		greeter = recommended_greeter(desktop)

	top_level = profile_handler.get_profile_by_name('Desktop')
	sub_profile = profile_handler.get_profile_by_name(desktop.value)

	if top_level is None or sub_profile is None:
		raise ValueError(
			f'Desktop profile "{desktop.value}" is not available in this archinstall build',
		)

	top_level.current_selection = [sub_profile]

	# Hyprland needs a seat-access manager; polkit is the pre-selected default
	# (matches the interactive selection flow in the upstream profile).
	if desktop == Desktop.HYPRLAND:
		sub_profile.custom_settings = {CustomSetting.SeatAccess: 'polkit'}

	return ProfileConfiguration(profile=top_level, greeter=greeter, gfx_driver=gfx_driver)


def desktop_from_profile(profile_config: ProfileConfiguration | None) -> Desktop | None:
	"""
	Reverse-map the *actually selected* profile back to a fork Desktop choice.

	This is what the runtime greeter/dotfile steps use, so changing the DE in
	the custom GlobalMenu stays consistent with the runtime extensions.
	"""
	profile = profile_config.profile if profile_config else None
	if profile is None:
		return None

	if isinstance(profile, MinimalProfile) or profile.name == 'Minimal':
		return Desktop.MINIMAL_CLI

	selections = profile.current_selection
	if not selections:
		return None

	for selection in selections:
		try:
			return Desktop(selection.name)
		except ValueError:
			continue

	return None


def apply_opinionated_defaults(config: ArchConfig, uefi: bool, skip_boot: bool) -> None:
	"""
	Pre-select the fork defaults (spec MODE B): ext4 default layout happens in
	the disk flow; here swap, bootloader, kernels, audio stack and pacman
	parallel downloads get their opinionated defaults when the user did not
	choose anything yet.
	"""
	if config.bootloader_config is None:
		config.bootloader_config = BootloaderConfiguration.get_default(uefi, skip_boot)

	if config.swap is None or not config.swap.enabled:
		config.swap = ZramConfiguration(enabled=True)

	if config.app_config is None:
		config.app_config = ApplicationConfiguration()
	if config.app_config.audio_config is None:
		config.app_config.audio_config = AudioConfiguration(Audio.PIPEWIRE)

	if config.pacman_config.parallel_downloads <= 1:
		config.pacman_config = PacmanConfiguration(parallel_downloads=10, color=True)


def assemble_preset_config(
	config: ArchConfig,
	locale_config: LocaleConfiguration,
	mirror_config: MirrorConfiguration | None,
	disk_config: DiskLayoutConfiguration,
	username: str,
	user_password: Password,
	options: PresetOptions,
	uefi: bool,
	skip_boot: bool,
	gpu_packages: list[str] | None = None,
) -> ArchConfig:
	"""
	Complete the ``ArchConfig`` for the Cal's Preset (MODE A) flow.

	Everything the guided installation consumes is derived from the prompted
	values plus the hard-coded preset options:

	* ext4 best-effort disk layout, zram swap, systemd-boot on UEFI
	* pipewire audio, paru handled at runtime (guarded), optional driver pkgs
	* user in ``wheel`` with full sudo, root password == user password
	* Hyprland profile with greetd + tuigreet as the greeter
	"""
	apply_opinionated_defaults(config, uefi, skip_boot)

	config.locale_config = locale_config
	config.mirror_config = mirror_config
	config.disk_config = disk_config
	config.hostname = config.hostname or username
	config.mode = SetupMode.PRESET

	config.preset = options

	user = User(
		username=username,
		password=user_password,
		sudo=True,
		groups=['wheel'],
	)

	# Default root password to match the primary user password (spec MODE A).
	# Keep the plaintext around when it is known so the two Password objects
	# compare equal; otherwise carry over the already-hashed value.
	config.auth_config = AuthenticationConfiguration(
		root_enc_password=Password(
			plaintext=user_password.plaintext,
			enc_password=user_password.enc_password,
		),
		users=[user],
	)

	config.profile_config = profile_config_for_desktop(
		options.desktop,
		greeter=options.greeter,
	)

	packages = list(gpu_packages or [])
	if options.dotfiles is not None:
		packages.append('git')
	if packages:
		config.packages = packages

	return config
