"""
Interactive prompts for the fork flows (spec §1).

Only this module talks to the TUI; everything derived from the answers is
assembled in :mod:`archinstall.preset.builder` and tested without a screen.
"""

import re

from archinstall.default_profiles.profile import GreeterType
from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.disk.disk_menu import suggest_single_disk_layout
from archinstall.lib.locale.locale_menu import LocaleMenu
from archinstall.lib.menu.helpers import Confirmation, Input, Selection
from archinstall.lib.menu.util import get_password
from archinstall.lib.models.device import (
	DeviceModification,
	DiskLayoutConfiguration,
	DiskLayoutType,
	FilesystemType,
)
from archinstall.lib.models.locale import LocaleConfiguration
from archinstall.lib.models.users import Password
from archinstall.lib.translationhandler import tr
from archinstall.preset.display_manager import greeter_display_name, recommended_greeter
from archinstall.preset.options import CachyosLevel, Desktop, Dotfiles, SetupMode
from archinstall.tui.menu_item import MenuItem, MenuItemGroup
from archinstall.tui.result import ResultType

_USERNAME_RE = re.compile(r'^[a-z_][a-z0-9_-]{0,31}$')
_BLOCKED_USERNAMES = {'root', 'greeter', 'nobody'}


async def select_setup_mode() -> SetupMode | None:
	"""Top-level entry choice presented at the very start of the installer."""
	items = [
		MenuItem(SetupMode.PRESET.display_name(), value=SetupMode.PRESET),
		MenuItem(SetupMode.CUSTOM.display_name(), value=SetupMode.CUSTOM),
	]
	group = MenuItemGroup(items, sort_items=False)
	group.set_selected_by_value(SetupMode.PRESET)

	result = await Selection[SetupMode](
		group,
		header=tr('How would you like to install Arch Linux?'),
		allow_skip=True,
	).show()

	match result.type_:
		case ResultType.Skip:
			return None
		case ResultType.Selection:
			return result.get_value()
		case _:
			return None


async def select_desktop_environment() -> Desktop | None:
	items = []
	for desktop in Desktop:
		label = desktop.value
		if desktop.recommended():
			label += ' (Recommended)'
		items.append(MenuItem(label, value=desktop))

	group = MenuItemGroup(items, sort_items=False)
	group.set_selected_by_value(Desktop.KDE_PLASMA)

	result = await Selection[Desktop](
		group,
		header=tr('Select a desktop environment'),
		allow_skip=True,
		preview_location='bottom',
	).show()

	match result.type_:
		case ResultType.Skip:
			return None
		case ResultType.Selection:
			return result.get_value()
		case _:
			return None


async def select_dotfiles_suite() -> Dotfiles | None:
	items = [MenuItem('None / Vanilla', value=None)]

	for dotfiles in Dotfiles:
		items.append(MenuItem(dotfiles.display_name(), value=dotfiles))

	group = MenuItemGroup(items, sort_items=False)
	group.set_selected_by_value(Dotfiles.AMBXST)

	result = await Selection[Dotfiles | None](
		group,
		header=tr('Select a Hyprland dotfiles suite (third-party, installed as your user)'),
		allow_skip=True,
	).show()

	match result.type_:
		case ResultType.Skip:
			return None
		case ResultType.Selection:
			return result.get_value()
		case _:
			return None


async def select_greeter(desktop: Desktop, preset: GreeterType | None) -> GreeterType | None:
	"""Greeter selection with the dynamic recommendation flagged + pre-selected."""
	recommended = recommended_greeter(desktop)

	if recommended is None:
		return None

	assert preset is not None

	items: list[MenuItem] = []
	seen: set[GreeterType] = set()

	for greeter in (recommended, GreeterType.Sddm, GreeterType.Gdm, GreeterType.Lightdm, GreeterType.Ly):
		if greeter in seen:
			continue
		seen.add(greeter)

		label = greeter_display_name(greeter)
		if greeter == recommended:
			hint = f'Recommended for {desktop.value}'
			if desktop == Desktop.HYPRLAND:
				hint = 'Recommended for Hyprland'
			elif desktop == Desktop.KDE_PLASMA:
				hint = 'Recommended for KDE Plasma'
			elif desktop == Desktop.GNOME:
				hint = 'Recommended for GNOME'
			label += f' ({hint})'

		items.append(MenuItem(label, value=greeter))

	group = MenuItemGroup(items, sort_items=False)
	group.set_selected_by_value(recommended)

	result = await Selection[GreeterType](
		group,
		header=tr('Select a display manager (greeter)'),
		allow_skip=True,
	).show()

	match result.type_:
		case ResultType.Skip:
			return preset
		case ResultType.Selection:
			return result.get_value()
		case _:
			return None


async def select_cachyos_repositories() -> CachyosLevel | None:
	"""
	Offer the CachyOS repositories (opinionated default: on).  The exact ISA
	level is detected automatically afterwards.
	"""
	header = tr(
		'Use the CachyOS repositories as the primary package providers?\\n\\n'
		'Recommended for performance-tuned packages. Choosing "no" keeps a '
		'vanilla Arch installation.',
	)

	result = await Confirmation(
		header=header,
		allow_skip=False,
		preset=True,
	).show()

	if not result.get_value():
		return None

	return CachyosLevel.GENERIC


async def prompt_user_credentials() -> tuple[str, Password] | None:
	"""Username + password with validation (used by the Cal preset flow)."""

	def validate_username(value: str | None) -> str | None:
		if not value:
			return tr('Input cannot be empty')

		if not _USERNAME_RE.match(value):
			return tr(
				'Username must start with a lowercase letter or underscore and contain only lowercase letters, digits, "-" or "_" (max 32 chars)',
			)

		if value in _BLOCKED_USERNAMES:
			return tr('This username is reserved')

		return None

	result = await Input(
		header=tr('Enter a username'),
		allow_skip=False,
		validator_callback=validate_username,
	).show()

	if result.type_ != ResultType.Selection:
		return None

	username = result.get_value()

	password = await get_password(
		header=tr('Enter a password for the user'),
		allow_skip=False,
	)

	if password is None:
		return None

	return username, password


async def select_target_disk() -> DiskLayoutConfiguration | None:
	"""
	Single 1-click target disk selection, then automatic best-effort
	partitioning with ext4 (no separate /home, swap handled via zram later).
	"""
	devices = device_handler.devices

	if not devices:
		return None

	def preview(item: MenuItem) -> str | None:
		from archinstall.lib.utils.format import as_table

		device = next((d for d in devices if d.device_info.path == item.value), None)
		if device and device.partition_infos:
			return as_table(device.partition_infos)
		return None

	items = [
		MenuItem(
			str(device.device_info.path),
			value=str(device.device_info.path),
			preview_action=preview,
		)
		for device in devices
	]

	group = MenuItemGroup(items, sort_items=False)

	result = await Selection[str](
		group,
		header=tr('Select the disk to install to (the whole disk will be used)'),
		allow_skip=True,
		preview_location='bottom',
	).show()

	match result.type_:
		case ResultType.Skip:
			return None
		case ResultType.Selection:
			selected_path = result.get_value()
		case _:
			return None

	device = next((d for d in devices if str(d.device_info.path) == selected_path), None)
	if device is None:
		return None

	modification: DeviceModification = await suggest_single_disk_layout(
		device,
		filesystem_type=FilesystemType.EXT4,
		separate_home=False,
	)

	return DiskLayoutConfiguration(
		config_type=DiskLayoutType.Default,
		device_modifications=[modification],
	)


async def select_locale() -> LocaleConfiguration | None:
	locale_config = await LocaleMenu(LocaleConfiguration.default()).show()
	return locale_config
