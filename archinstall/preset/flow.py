"""
Flow orchestration for the fork entry screen (spec §1).

``run_entry`` is invoked by the guided script before the installation; it
routes into either the automated Cal's Preset collection or the custom
setup wizard.  Both modes are strictly linear prompt sequences - no nested
menu - and a ``recollect`` pass re-runs the sequence with the previous
answers pre-filled so the user can revise them.
"""

import sys

from archinstall.lib.args import ArchConfigHandler
from archinstall.lib.hardware import GfxDriver, SysInfo
from archinstall.lib.log import debug, error, info
from archinstall.lib.mirror.mirror_handler import MirrorListHandler
from archinstall.preset import detect
from archinstall.preset.builder import apply_opinionated_defaults, assemble_config, profile_config_for_desktop
from archinstall.preset.cachyos import detected_level
from archinstall.preset.display_manager import recommended_greeter
from archinstall.preset.mirrors import rank_mirrors_with_reflector
from archinstall.preset.options import CachyosLevel, Desktop, Dotfiles, GpuPlan, PresetOptions, SetupMode
from archinstall.preset.wizard import (
	prompt_user_credentials,
	select_cachyos_repositories,
	select_desktop_environment,
	select_dotfiles_suite,
	select_greeter,
	select_locale,
	select_setup_mode,
	select_target_disk,
)
from archinstall.tui.components import tui


def run_entry(
	arch_config_handler: ArchConfigHandler,
	mirror_list_handler: MirrorListHandler,
	recollect: bool = False,
) -> None:
	"""
	Top-level entry: Cal's Preset vs. Custom Setup.

	Only runs for interactive launches without a pre-existing mode selection.
	``recollect=True`` re-runs the prompt sequence of the *already chosen*
	mode so the user can revise answers after aborting the final confirmation
	screen (the mode question itself is not repeated).
	"""
	config = arch_config_handler.config

	if recollect and config.mode is not None:
		# Re-entry after a confirmation abort: the mode question is shown
		# again with the previous choice pre-focused so one Enter keeps it
		# and the user can still switch between Preset and Custom.
		preset_flow = tui.run(lambda: select_setup_mode(preset=config.mode))

		if preset_flow is None:
			sys.exit(0)

		config.mode = preset_flow
	else:
		preset_flow = tui.run(select_setup_mode)

		if preset_flow is None:
			sys.exit(0)

		config.mode = preset_flow

	if preset_flow == SetupMode.PRESET:
		ok = tui.run(lambda: _collect_cal_preset(arch_config_handler, mirror_list_handler, recollect=recollect))
	elif preset_flow == SetupMode.CUSTOM:
		ok = tui.run(lambda: _collect_custom_preferences(arch_config_handler, recollect=recollect))
	else:  # pragma: no cover - defensive
		raise ValueError(f'Unknown setup mode: {preset_flow}')

	if not ok:
		sys.exit(0)


async def _collect_cal_preset(
	arch_config_handler: ArchConfigHandler,
	mirror_list_handler: MirrorListHandler,
	recollect: bool = False,
) -> bool:
	"""MODE A: minimal prompts, everything else hard-coded by the preset."""
	config = arch_config_handler.config
	debug('Collecting Cal preset choices (locale -> mirrors -> credentials -> disk)')

	# On a recollect pass, pre-seed prompts with the previously chosen values.
	prev_username = config.auth_config.users[0].username if config.auth_config and config.auth_config.users else None

	locale_config = await select_locale(preset=config.locale_config if recollect else None)
	if locale_config is None:
		error('Cal preset aborted: no locale selected')
		return False

	info('Auto-ranking Arch mirrors via reflector (best effort)...')
	mirror_config = rank_mirrors_with_reflector()

	credentials = await prompt_user_credentials(preset_username=prev_username)
	if credentials is None:
		error('Cal preset aborted: no credentials provided')
		return False

	username, user_password = credentials

	disk_config = await select_target_disk(preset=config.disk_config if recollect else None)
	if disk_config is None:
		error('Cal preset aborted: no target disk selected')
		return False

	# GPU detection (best-effort; the runtime falls back to generic mesa) and
	# CPU ISA detection for the CachyOS repositories.
	devices = detect.probe_pci_devices()
	plan, packages = detect.gpu_plan(devices)

	options = PresetOptions.cal_preset()
	options.cachyos = _level_from_detection(detected_level())
	options.detected_gpu_plan = plan
	options.detected_gpu_packages = packages
	options.deploy_dotfiles = True
	options.use_paru = True

	assemble_config(
		config,
		locale_config,
		mirror_config,
		disk_config,
		username,
		user_password,
		options,
		uefi=SysInfo.has_uefi(),
		skip_boot=arch_config_handler.args.skip_boot,
		gpu_packages=packages,
	)

	info('Cal preset configuration collected: ' + ', '.join(options.summary()))
	return True


async def _collect_custom_preferences(
	arch_config_handler: ArchConfigHandler,
	recollect: bool = False,
) -> bool:
	"""
	MODE B: the same linear sequence as the Cal preset, but with the user
	choosing every step.  No nested menu: locale -> mirrors -> repositories ->
	desktop -> (dotfiles + greeter for desktops) -> credentials -> disk.
	"""
	config = arch_config_handler.config

	if config.profile_config is not None and not recollect:
		# Re-entry with a pre-populated config (e.g. --config): keep it.
		return True

	apply_opinionated_defaults(
		config,
		uefi=SysInfo.has_uefi(),
		skip_boot=arch_config_handler.args.skip_boot,
	)

	# On a recollect pass, pre-seed every prompt with the previously chosen
	# values so the sequence revises instead of restarting from scratch.
	previous = config.preset
	prev_desktop = previous.desktop if previous is not None else None
	prev_username = config.auth_config.users[0].username if config.auth_config and config.auth_config.users else None

	locale_config = await select_locale(preset=config.locale_config if recollect else None)
	if locale_config is None:
		error('Custom setup aborted: no locale selected')
		return False

	config.locale_config = locale_config

	if config.mirror_config is None:
		info('Auto-ranking Arch mirrors via reflector (best effort)...')
		mirror_config = rank_mirrors_with_reflector()
		if mirror_config is not None:
			config.mirror_config = mirror_config

	cachyos_level = await select_cachyos_repositories(
		preset=previous.cachyos is not None if previous is not None else True,
	)
	desktop = await select_desktop_environment(preset=prev_desktop)

	if desktop is None:
		error('Custom setup aborted: no desktop environment selected')
		return False

	# Minimal CLI bypasses the DE/DM/dotfile prompts cleanly.
	dotfiles: Dotfiles | None = None
	greeter: GreeterType | None = None

	if desktop.is_desktop_env():
		if desktop == Desktop.HYPRLAND:
			dotfiles = await select_dotfiles_suite(preset=previous.dotfiles if previous is not None else Dotfiles.AMBXST)

		greeter = await select_greeter(desktop, recommended_greeter(desktop), chosen=previous.greeter if previous is not None else None)

	credentials = await prompt_user_credentials(preset_username=prev_username)
	if credentials is None:
		error('Custom setup aborted: no credentials provided')
		return False

	username, user_password = credentials

	disk_config = await select_target_disk(preset=config.disk_config if recollect else None)
	if disk_config is None:
		error('Custom setup aborted: no target disk selected')
		return False

	# GPU detection (best-effort; the runtime falls back to generic mesa).
	devices = detect.probe_pci_devices()
	plan, packages = detect.gpu_plan(devices)

	options = PresetOptions(
		mode=SetupMode.CUSTOM,
		desktop=desktop,
		dotfiles=dotfiles,
		greeter=greeter if greeter is not None else recommended_greeter(desktop),
		cachyos=cachyos_level,
	)
	options.cachyos = _upgrade_detected_level(cachyos_level)
	options.detected_gpu_plan = plan
	options.detected_gpu_packages = packages
	options.deploy_dotfiles = True
	options.use_paru = True

	# Auto-detect the graphics driver for the profile (best effort; the
	# opinionated selection remains visible in the confirmation summary).
	gfx_driver = _gfx_driver_from_hardware() if desktop.is_desktop_env() else None

	assemble_config(
		config,
		locale_config,
		None,  # mirrors were stashed above; never clobber them here
		disk_config,
		username,
		user_password,
		options,
		uefi=SysInfo.has_uefi(),
		skip_boot=arch_config_handler.args.skip_boot,
		gpu_packages=packages,
	)

	config.profile_config = profile_config_for_desktop(
		desktop,
		greeter=options.greeter,
		gfx_driver=gfx_driver,
	)

	info('Custom setup configuration collected: ' + ', '.join(options.summary()))
	return True


def _gfx_driver_from_hardware() -> GfxDriver | None:
	"""Map live GPU detection onto archinstall's driver enum (best effort)."""
	devices = detect.probe_pci_devices()
	plan, _ = detect.gpu_plan(devices)

	match plan:
		case GpuPlan.AMD:
			return GfxDriver.AmdOpenSource
		case GpuPlan.INTEL:
			return GfxDriver.IntelOpenSource
		case GpuPlan.VM:
			return GfxDriver.VMOpenSource
		case GpuPlan.NVIDIA_OPEN:
			return GfxDriver.NvidiaOpenKernel
		case GpuPlan.NVIDIA_LEGACY:
			return GfxDriver.NvidiaOpenSource
		case GpuPlan.GENERIC_MESA | GpuPlan.HYBRID:
			# Hybrid NVIDIA configs cannot be expressed by the enum; the
			# open-source union (or a manual choice in the Profile menu) is the
			# safest default.
			return GfxDriver.AllOpenSource


def _level_from_detection(detected: str | None) -> CachyosLevel:
	if detected is None:
		return CachyosLevel.GENERIC
	return CachyosLevel(detected)


def _upgrade_detected_level(selected: CachyosLevel | None) -> CachyosLevel | None:
	"""Keep the user opt-out, upgrade GENERIC when detection found a level."""
	if selected is None:
		return None

	if selected != CachyosLevel.GENERIC:
		return selected

	return _level_from_detection(detected_level())
