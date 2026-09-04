"""
Flow orchestration for the fork entry screen (spec §1).

``run_entry`` is invoked by the guided script before the GlobalMenu; it routes
into either the automated Cal's Preset collection or the custom setup wizard.
"""

import sys

from archinstall.lib.args import ArchConfigHandler
from archinstall.lib.hardware import GfxDriver, SysInfo
from archinstall.lib.log import debug, error, info
from archinstall.lib.mirror.mirror_handler import MirrorListHandler
from archinstall.preset import detect
from archinstall.preset.builder import apply_opinionated_defaults, assemble_preset_config, profile_config_for_desktop
from archinstall.preset.cachyos import detected_level
from archinstall.preset.display_manager import recommended_greeter
from archinstall.preset.mirrors import rank_mirrors_with_reflector
from archinstall.preset.options import CachyosLevel, Desktop, GpuPlan, PresetOptions, SetupMode
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
) -> None:
	"""
	Top-level entry: Cal's Preset vs. Custom Setup.

	Only runs for interactive launches without a pre-existing mode selection.
	"""
	config = arch_config_handler.config
	preset_flow = tui.run(select_setup_mode)

	if preset_flow is None:
		sys.exit(0)

	config.mode = preset_flow

	if preset_flow == SetupMode.PRESET:
		ok = tui.run(lambda: _collect_cal_preset(arch_config_handler, mirror_list_handler))
	elif preset_flow == SetupMode.CUSTOM:
		ok = tui.run(lambda: _collect_custom_preferences(arch_config_handler))
	else:  # pragma: no cover - defensive
		raise ValueError(f'Unknown setup mode: {preset_flow}')

	if not ok:
		sys.exit(0)


async def _collect_cal_preset(
	arch_config_handler: ArchConfigHandler,
	mirror_list_handler: MirrorListHandler,
) -> bool:
	"""MODE A: minimal prompts, everything else hard-coded by the preset."""
	config = arch_config_handler.config
	debug('Collecting Cal preset choices (locale -> mirrors -> credentials -> disk)')

	locale_config = await select_locale()
	if locale_config is None:
		error('Cal preset aborted: no locale selected')
		return False

	info('Auto-ranking Arch mirrors via reflector (best effort)...')
	mirror_config = rank_mirrors_with_reflector()

	credentials = await prompt_user_credentials()
	if credentials is None:
		error('Cal preset aborted: no credentials provided')
		return False

	username, user_password = credentials

	disk_config = await select_target_disk()
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

	assemble_preset_config(
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


async def _collect_custom_preferences(arch_config_handler: ArchConfigHandler) -> bool:
	"""
	MODE B: DE selection, dotfile choice for Hyprland and the dynamic greeter
	recommendation.  Filesystem/tooling defaults are pre-selected on the config
	and everything else remains configurable through the GlobalMenu.
	"""
	config = arch_config_handler.config

	if config.profile_config is not None:
		# Re-entry after a GlobalMenu abort: preferences are already collected.
		return True

	apply_opinionated_defaults(
		config,
		uefi=SysInfo.has_uefi(),
		skip_boot=arch_config_handler.args.skip_boot,
	)

	cachyos_level = await select_cachyos_repositories()
	desktop = await select_desktop_environment()

	if desktop is None:
		error('Custom setup aborted: no desktop environment selected')
		return False

	# Minimal CLI bypasses the DE/DM/dotfile prompts cleanly.
	if not desktop.is_desktop_env():
		config.profile_config = profile_config_for_desktop(desktop)
		config.preset = PresetOptions(
			mode=SetupMode.CUSTOM,
			desktop=Desktop.MINIMAL_CLI,
			dotfiles=None,
			greeter=None,
			cachyos=cachyos_level,
		)
		return True

	dotfiles = None
	if desktop == Desktop.HYPRLAND:
		dotfiles = await select_dotfiles_suite()

	recommended = recommended_greeter(desktop)
	greeter = await select_greeter(desktop, recommended)

	# Auto-detect the graphics driver so the Profile menu opens with the
	# opinionated selection already applied (still fully overridable there).
	gfx_driver = _gfx_driver_from_hardware()

	config.profile_config = profile_config_for_desktop(desktop, greeter=greeter, gfx_driver=gfx_driver)

	options = PresetOptions(
		mode=SetupMode.CUSTOM,
		desktop=desktop,
		dotfiles=dotfiles,
		greeter=greeter if greeter is not None else recommended,
		cachyos=cachyos_level,
	)
	options.cachyos = _upgrade_detected_level(cachyos_level)
	config.preset = options

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
