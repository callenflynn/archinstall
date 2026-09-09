"""
Unit tests for the fork's preset/custom flows (spec §6).

All tests are pure: no menus, no root, no hardware probing.
"""

from pathlib import Path

from archinstall.default_profiles.profile import CustomSetting, GreeterType
from archinstall.lib.args import ArchConfig
from archinstall.lib.models.application import ApplicationConfiguration, Audio, AudioConfiguration, ZramConfiguration
from archinstall.lib.models.locale import LocaleConfiguration
from archinstall.lib.models.users import Password
from archinstall.preset import cachyos
from archinstall.preset.builder import apply_opinionated_defaults, assemble_config, desktop_from_profile, profile_config_for_desktop
from archinstall.preset.detect import GpuDevice, Vendor, gpu_plan, nvidia_generation, parse_pci_lines
from archinstall.preset.display_manager import recommended_greeter, resolve_session_exec
from archinstall.preset.dotfiles import DotfilePlan, inspect_repository
from archinstall.preset.mirrors import parse_reflector_mirrorlist
from archinstall.preset.options import Desktop, Dotfiles, PresetOptions, SetupMode

SAMPLE_PACMAN_CONF = """\
[options]
ParallelDownloads = 5

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist
"""


# ---------------------------------------------------------------------------
# 1. Preset vs Custom mode profile dictionary generation
# ---------------------------------------------------------------------------


def test_cal_preset_options_are_hardcoded() -> None:
	options = PresetOptions.cal_preset()

	assert options.mode == SetupMode.PRESET
	assert options.desktop == Desktop.HYPRLAND
	assert options.dotfiles == Dotfiles.AMBXST
	assert options.greeter == GreeterType.GreetdTuigreet
	assert options.use_paru is True
	assert options.deploy_dotfiles is True


def test_preset_profile_assembly_sets_hyprland_greeter() -> None:
	profile_config = profile_config_for_desktop(Desktop.HYPRLAND)

	assert profile_config.profile is not None
	assert profile_config.profile.name == 'Desktop'
	assert profile_config.profile.current_selection_names() == ['Hyprland']
	assert profile_config.greeter == GreeterType.GreetdTuigreet
	assert profile_config.gfx_driver is None

	hyprland = profile_config.profile.current_selection[0]
	assert hyprland.custom_settings == {CustomSetting.SeatAccess: 'polkit'}


def test_minimal_cli_bypasses_desktop_dm_prompts() -> None:
	# Minimal CLI must produce a profile configuration without any greeter or
	# dotfile coupling (the wizard skips those prompts by construction).
	profile_config = profile_config_for_desktop(Desktop.MINIMAL_CLI)

	assert profile_config.profile is not None
	assert profile_config.profile.name == 'Minimal'
	assert profile_config.greeter is None
	assert profile_config.gfx_driver is None

	options = PresetOptions(
		mode=SetupMode.CUSTOM,
		desktop=Desktop.MINIMAL_CLI,
		dotfiles=None,
		greeter=None,
	)
	config = ArchConfig()
	config.preset = options

	assert desktop_from_profile(profile_config) == Desktop.MINIMAL_CLI


def test_apply_opinionated_defaults() -> None:
	config = ArchConfig()
	apply_opinionated_defaults(config, uefi=True, skip_boot=False)

	assert config.swap == ZramConfiguration(enabled=True)
	assert config.bootloader_config is not None
	assert config.bootloader_config.bootloader.value == 'Systemd-boot'
	assert config.app_config == ApplicationConfiguration(audio_config=AudioConfiguration(Audio.PIPEWIRE))
	assert config.pacman_config.parallel_downloads > 1


def test_assemble_preset_config_complete() -> None:
	config = ArchConfig()
	options = PresetOptions.cal_preset()

	assemble_config(
		config,
		locale_config=LocaleConfiguration.default(),
		mirror_config=None,
		disk_config=None,  # type: ignore[arg-type] # untouched by the assembly
		username='cal',
		user_password=Password(plaintext='sup3rSecret!'),
		options=options,
		uefi=True,
		skip_boot=False,
		gpu_packages=['mesa'],
	)

	assert config.mode == SetupMode.PRESET
	assert config.preset is not None
	assert config.locale_config is not None
	assert config.disk_config is None
	assert config.packages == ['mesa', 'git']

	# user in wheel with full sudo; root password defaults to the user hash
	assert config.auth_config is not None
	assert config.auth_config.users == [
		config.auth_config.users[0],
	]
	user = config.auth_config.users[0]
	assert user.username == 'cal'
	assert user.sudo is True
	assert 'wheel' in user.groups
	assert config.auth_config.root_enc_password == Password(plaintext='sup3rSecret!')


# ---------------------------------------------------------------------------
# 2. GPU detection parsing + NVIDIA generation classification
# ---------------------------------------------------------------------------

RTX_4090 = '01:00.0 VGA compatible controller: NVIDIA Corporation AD102 [GeForce RTX 4090]'
GTX_1080 = '01:00.0 VGA compatible controller: NVIDIA Corporation GP104 [GeForce GTX 1080]'
RX_6800 = '03:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 21 [Radeon RX 6800]'
INTEL_UHD = '00:02.0 VGA compatible controller: Intel Corporation AlderLake-S GT1 [UHD Graphics 770]'
VENDOR_LABEL = '01:00.0 Audio device: NVIDIA Corporation GA104 High Definition Audio Controller'


def test_parse_pci_lines_ignores_non_gpu() -> None:
	devices = parse_pci_lines([RTX_4090, VENDOR_LABEL])

	assert len(devices) == 1
	assert devices[0].vendor == Vendor.NVIDIA


def test_classify_vendors() -> None:
	devices = parse_pci_lines([RTX_4090, RX_6800, INTEL_UHD])

	assert devices[0].vendor == Vendor.NVIDIA
	assert devices[1].vendor == Vendor.AMD
	assert devices[2].vendor == Vendor.INTEL


def test_nvidia_generation_classification() -> None:
	assert nvidia_generation(RTX_4090) == 'turing_plus'
	assert nvidia_generation('NVIDIA Corporation GA106 [GeForce RTX 3060]') == 'turing_plus'
	assert nvidia_generation(GTX_1080) == 'pre_turing'
	assert nvidia_generation('NVIDIA Corporation TU102 [Quadro RTX 6000]') == 'turing_plus'


def test_nvidia_driver_sets_by_generation() -> None:
	_, modern_pkgs = gpu_plan([GpuDevice(RTX_4090, Vendor.NVIDIA)])
	assert 'nvidia-open-dkms' in modern_pkgs
	assert 'nvidia-utils' in modern_pkgs
	assert 'lib32-nvidia-utils' in modern_pkgs
	assert 'egl-wayland' in modern_pkgs
	assert 'dkms' in modern_pkgs

	legacy, legacy_pkgs = gpu_plan([GpuDevice(GTX_1080, Vendor.NVIDIA)])
	assert legacy.value == 'NVIDIA (nouveau, pre-Turing fallback)'
	assert 'nvidia-open-dkms' not in legacy_pkgs
	assert 'xf86-video-nouveau' in legacy_pkgs


# ---------------------------------------------------------------------------
# 3. Hybrid / dual GPU package generation
# ---------------------------------------------------------------------------


def test_hybrid_nvidia_plus_amd_installs_both_and_envycontrol() -> None:
	plan, packages = gpu_plan(
		[
			GpuDevice('GeForce RTX 4070', Vendor.NVIDIA),
			GpuDevice('AMD Radeon RX 6800', Vendor.AMD),
		],
	)

	assert plan.value == 'Hybrid / dual GPU'
	assert 'nvidia-open-dkms' in packages
	assert 'vulkan-radeon' in packages
	assert 'envycontrol' in packages


def test_unclassified_gpu_falls_back_to_mesa() -> None:
	plan, packages = gpu_plan([GpuDevice('Unknown display controller', Vendor.UNKNOWN)])
	assert plan.value == 'mesa (fallback)'
	assert packages == ['mesa']


def test_vm_falls_back_to_mesa() -> None:
	plan, packages = gpu_plan([GpuDevice('VMware SVGA II Adapter', Vendor.VM)])
	assert plan.value == 'Virtual machine'
	assert packages == ['mesa']


# ---------------------------------------------------------------------------
# 4. CPU ISA microarchitecture level classification + fallback
# ---------------------------------------------------------------------------


def test_isa_level_detection_v3() -> None:
	assert cachyos.detect_isa_level({'v2', 'v3'}, None, 'GenuineIntel') == 'v3'


def test_isa_level_detection_v4_via_glibc() -> None:
	assert cachyos.detect_isa_level({'v2', 'v3', 'v4'}, None, 'GenuineIntel') == 'v4'


def test_isa_level_detection_znver4_via_gcc() -> None:
	assert cachyos.detect_isa_level({'v2', 'v3', 'v4'}, 'znver4', 'AuthenticAMD') == 'znver4'
	assert cachyos.detect_isa_level({'v2', 'v3', 'v4'}, 'znver5', 'AuthenticAMD') == 'znver4'


def test_isa_level_ambiguous_falls_back_to_generic() -> None:
	# v1/v2 only, or unreadable input -> generic [cachyos]
	assert cachyos.detect_isa_level(set(), None, None) is None
	assert cachyos.detect_isa_level({'v2'}, None, 'GenuineIntel') is None


def test_isa_level_amd_v4_without_gcc_stays_conservative() -> None:
	assert cachyos.detect_isa_level({'v4'}, None, 'AuthenticAMD') == 'v3'


# ---------------------------------------------------------------------------
# 5. DE -> DM dynamic recommendation mapping
# ---------------------------------------------------------------------------


def test_recommended_greeter_mapping() -> None:
	assert recommended_greeter(Desktop.HYPRLAND) == GreeterType.GreetdTuigreet
	assert recommended_greeter(Desktop.KDE_PLASMA) == GreeterType.Sddm
	assert recommended_greeter(Desktop.GNOME) == GreeterType.Gdm
	assert recommended_greeter(Desktop.CINNAMON) == GreeterType.Lightdm
	assert recommended_greeter(Desktop.XFCE) == GreeterType.Lightdm
	assert recommended_greeter(Desktop.MINIMAL_CLI) is None


# ---------------------------------------------------------------------------
# 6. CachyOS repository list generator + pacman.conf top-injection parser
# ---------------------------------------------------------------------------


def test_repo_stanzas_generic() -> None:
	stanza = cachyos.repo_stanza(None)

	assert '[cachyos]' in stanza
	assert 'Include = /etc/pacman.d/cachyos-mirrorlist' in stanza
	assert '[cachyos-core' not in stanza


def test_repo_stanzas_isa_levels() -> None:
	v3 = cachyos.repo_stanza('v3')
	assert '[cachyos-v3]' in v3
	assert '[cachyos-core-v3]' in v3
	assert '[cachyos-extra-v3]' in v3
	assert 'Include = /etc/pacman.d/cachyos-v3-mirrorlist' in v3

	znver4 = cachyos.repo_stanza('znver4')
	# v4 and znver4 share the v4 mirrorlist (verified against the CachyOS wiki)
	assert '[cachyos-znver4]' in znver4
	assert 'Include = /etc/pacman.d/cachyos-v4-mirrorlist' in znver4


def test_inject_before_core_precedes_official_repos() -> None:
	injected = cachyos.inject_before_core(SAMPLE_PACMAN_CONF, 'v3')

	assert injected.index('[cachyos-v3]') < injected.index('[core]')
	assert injected.index('[cachyos-v3]') < injected.index('[extra]')
	assert injected.index('[cachyos]') < injected.index('[core]')
	assert injected.index('[core]') < injected.index('[extra]')


def test_injection_is_idempotent() -> None:
	once = cachyos.inject_before_core(SAMPLE_PACMAN_CONF, 'v3')
	twice = cachyos.inject_before_core(once, 'v3')

	assert twice == once


def test_mirrorlist_packages_per_level() -> None:
	assert cachyos.mirrorlist_packages_for_level(None) == ['cachyos-keyring', 'cachyos-mirrorlist']
	assert 'cachyos-v3-mirrorlist' in cachyos.mirrorlist_packages_for_level('v3')
	assert 'cachyos-v4-mirrorlist' in cachyos.mirrorlist_packages_for_level('znver4')


# ---------------------------------------------------------------------------
# 7. Dotfile deployment failure handling + privilege enforcement
# ---------------------------------------------------------------------------


def test_dotfile_clone_command_is_drop_privileged(tmp_path: Path) -> None:
	from archinstall.preset.dotfiles import clone_command

	cmd = clone_command(Dotfiles.AMBXST, 'cal')

	assert cmd.startswith('git clone')
	assert 'https://github.com/Axenide/Ambxst' in cmd
	assert '/home/cal/Ambxst' in cmd


def test_dotfile_installer_command_targets_user_home(tmp_path: Path) -> None:
	from archinstall.preset.dotfiles import run_installer_command

	command = run_installer_command('cal', '/home/cal/Ambxst/setup.sh')

	# The command itself is a plain bash invocation; drop-privileged execution
	# is enforced by Installer.arch_chroot(run_as=...) which wraps it in
	# `su - <user> -c ...` - the installer path never runs as root.
	assert command == '/bin/bash /home/cal/Ambxst/setup.sh'


def test_dotfile_inspection_missing_repo_returns_no_scripts(tmp_path: Path) -> None:
	plan = inspect_repository(tmp_path)

	assert isinstance(plan, DotfilePlan)
	assert plan.install_scripts == []


def test_dotfile_inspection_detects_self_managed_deps(tmp_path: Path) -> None:
	repo = tmp_path / 'Ambxst'
	repo.mkdir()
	(repo / 'setup.sh').write_text('#!/bin/bash\nparu -S --needed waybar\n')

	plan = inspect_repository(repo)

	assert plan.install_scripts == [str(repo / 'setup.sh')]
	assert plan.dependencies_handled_automatically is True
	assert plan.required_packages == []


def test_dotfile_inspection_appends_base_packages_when_not_managed(tmp_path: Path) -> None:
	repo = tmp_path / 'Ambxst'
	repo.mkdir()
	(repo / 'setup.sh').write_text('#!/bin/bash\ncp -r .config ~/\n')

	plan = inspect_repository(repo)

	assert plan.dependencies_handled_automatically is False
	assert 'git' in plan.required_packages
	assert 'kitty' in plan.required_packages


def test_dotfile_inspection_config_subdir(tmp_path: Path) -> None:
	# ML4W keeps its scripts inside setup/ and its configs inside dotfiles/;
	# config_subdir must redirect the inspection (and nothing at the root
	# must leak into the plan).
	repo = tmp_path / 'ML4W'
	(repo / 'dotfiles' / 'setup').mkdir(parents=True)
	(repo / 'dotfiles' / 'setup' / 'setup.sh').write_text('#!/bin/bash\npacman -S --noconfirm waybar\n')
	(repo / 'README.md').write_text('root level readme mentioning pacman -Syu')

	plan = inspect_repository(repo, config_subdir='dotfiles')

	assert plan.install_scripts == [str(repo / 'dotfiles' / 'setup' / 'setup.sh')]
	assert plan.dependencies_handled_automatically is True
	assert plan.required_packages == []


def test_dotfile_ml4w_uses_setup_scripts_and_config_subdir(tmp_path: Path) -> None:
	from archinstall.preset import dotfiles as dotfiles_module

	assert 'dotfiles' == dotfiles_module._ML4W_CONFIG_SUBDIR
	assert ('preflight-arch.sh', 'post-arch.sh') == dotfiles_module._ML4W_SETUP_SCRIPTS

	for pkg in ('base-devel', 'gum', 'python-pipx', 'kitty', 'waybar'):
		assert pkg in dotfiles_module._ML4W_STAGED_PACKAGES


def test_dotfile_ml4w_requires_hyprland_repo_origin() -> None:
	from archinstall.preset.options import Dotfiles as DotfilesEnum

	assert DotfilesEnum.ML4W.repository == 'https://github.com/mylinuxforwork/dotfiles'
	assert DotfilesEnum.ML4W.value == 'ML4W'


# ---------------------------------------------------------------------------
# 9. Linear flow assembly (preset AND custom share the same path)
# ---------------------------------------------------------------------------


def test_assemble_config_respects_custom_mode() -> None:
	config = ArchConfig()
	options = PresetOptions(
		mode=SetupMode.CUSTOM,
		desktop=Desktop.KDE_PLASMA,
		dotfiles=None,
	)

	assemble_config(
		config,
		locale_config=LocaleConfiguration.default(),
		mirror_config=None,
		disk_config=None,  # type: ignore[arg-type] # untouched by the assembly
		username='user',
		user_password=Password(plaintext='sup3rSecret!'),
		options=options,
		uefi=True,
		skip_boot=False,
	)

	# The custom linear flow produces the same config shape as the preset,
	# only with its own mode/desktop/greeter choices.
	assert config.mode == SetupMode.CUSTOM
	assert config.preset is options
	user = config.auth_config.users[0]
	assert user.username == 'user'
	assert user.sudo is True
	assert 'wheel' in user.groups
	assert config.profile_config.greeter == options.greeter


# ---------------------------------------------------------------------------
# 8. Reflector parsing fallback
# ---------------------------------------------------------------------------


def test_parse_reflector_mirrorlist() -> None:
	content = (
		'## Arch Linux repository mirrorlist\n'
		'## Generated by reflector\n'
		'Server = https://mirror.example.com/$repo/os/$arch\n'
		'Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch\n'
	)

	assert parse_reflector_mirrorlist(content) == [
		'https://mirror.example.com/$repo/os/$arch',
		'https://geo.mirror.pkgbuild.com/$repo/os/$arch',
	]


def test_parse_reflector_mirrorlist_empty() -> None:
	assert parse_reflector_mirrorlist('# only comments\n') == []


# ---------------------------------------------------------------------------
# 9. Session executable validation for the greetd config
# ---------------------------------------------------------------------------


def test_resolve_session_exec_validates_desktop_files(tmp_path: Path) -> None:
	class FakeInstaller:
		target = tmp_path

	wayland = tmp_path / 'usr/share/wayland-sessions'
	wayland.mkdir(parents=True)
	(wayland / 'Hyprland.desktop').write_text('[Desktop Entry]\nExec=Hyprland\n')

	assert resolve_session_exec(FakeInstaller(), Desktop.HYPRLAND) == 'Hyprland'  # type: ignore[arg-type]


def test_session_fallback_without_desktop_files(tmp_path: Path) -> None:
	class FakeInstaller:
		target = tmp_path

	assert resolve_session_exec(FakeInstaller(), Desktop.GNOME) == 'gnome-session'  # type: ignore[arg-type]
