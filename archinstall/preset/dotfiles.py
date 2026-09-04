"""
Secured dotfile deployment (spec §4).

Third-party dotfile repositories are treated as **untrusted input**:

1. cloned into ``/home/<username>/`` inside the *target* chroot,
2. inspected (README + install scripts) to decide whether dependencies are
managed by the project itself or must be appended to the pacman transaction
beforehand,
3. executed strictly drop-privileged as the target user via ``su - <username>``
(never as root, never ``curl | sh``),
4. followed by a recursive ownership repair on success *and* failure.

Failure handling (spec §5): clone, dependency or script failures are logged,
home-directory ownership is repaired, and the installation continues with a
vanilla (un-dotted) desktop.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from archinstall.lib.exceptions import SysCallError
from archinstall.lib.log import debug, info, warn
from archinstall.preset.options import Dotfiles

if TYPE_CHECKING:
	from archinstall.lib.installer import Installer

# Installer scripts that dotfile projects commonly expect users to run.
_INSTALL_SCRIPT_NAMES = ('setup.sh', 'install.sh', 'install.fish', 'setup')

# Prerequisite base packages that Hyprland ricing suites commonly need even
# when their scripts install most of the fancy tooling.  git is always needed
# for the clone itself and therefore always part of the transaction.
_COMMON_DEPENDENCIES = ['git', 'kitty', 'waybar', 'rofi-wayland']

# Package manager invocations that indicate a script manages its own deps.
_PACKAGE_MANAGER_RE = re.compile(r'\b(pacman|paru|yay|apt-get|dnf)\b')


@dataclass(frozen=True)
class DotfilePlan:
	"""
	Static inspection result of a cloned repository (nothing executed).
	"""

	install_scripts: list[str] = field(default_factory=list)
	dependencies_handled_automatically: bool = False
	required_packages: list[str] = field(default_factory=list)


def clone_command(dotfiles: Dotfiles, username: str) -> str:
	"""
	git clone command executed *inside the target chroot* as the user.

	Running the clone as the user (not root) means every file already carries
	the correct ownership and no repository script ever runs with elevated
	rights, not even during download hooks.
	"""
	return f'git clone --depth 1 {dotfiles.repository} /home/{username}/{dotfiles.value}'


def run_installer_command(username: str, script_path: str) -> str:
	"""
	Drop-privileged installer invocation (spec: NEVER as root).

	``script_path`` is the path inside the chroot; the wrapper is executed via
	``su - <username> -c <cmd>`` by :meth:`Installer.arch_chroot`.
	"""
	return f'/bin/bash {script_path}'


def inspect_repository(repo_path: Path) -> DotfilePlan:
	"""
	Inspect a freshly cloned (untrusted) repository from the live filesystem.

	Reads the README and installer scripts - never executes them - and decides
	whether the project handles its own dependencies (i.e. its scripts call a
	package manager).  When it does not, the conservative prerequisite package
	set is appended to the pacman transaction before execution.
	"""
	install_scripts: list[str] = []
	deps_handled = False
	text = ''

	for name in _INSTALL_SCRIPT_NAMES:
		script = repo_path / name
		if not script.is_file():
			continue

		install_scripts.append(str(script))
		debug(f'Inspected installer script {script}')

		try:
			content = script.read_text()
		except OSError:
			continue

		if _PACKAGE_MANAGER_RE.search(content):
			deps_handled = True

	for name in ('README.md', 'readme.md', 'README'):
		readme = repo_path / name
		if readme.is_file():
			try:
				text += readme.read_text()
			except OSError:
				continue

	if _PACKAGE_MANAGER_RE.search(text) and 'manual' not in text.lower():
		deps_handled = True

	if deps_handled:
		debug('Dotfile project manages its own dependencies; nothing appended to the pacman transaction')
		return DotfilePlan(install_scripts=install_scripts, dependencies_handled_automatically=True)

	return DotfilePlan(
		install_scripts=install_scripts,
		dependencies_handled_automatically=False,
		required_packages=list(_COMMON_DEPENDENCIES),
	)


def deploy(
	installation: Installer,
	dotfiles: Dotfiles,
	username: str,
) -> bool:
	"""
	Deploy a dotfile suite for ``username`` inside the target.

	Returns ``True`` on success; ``False`` when the routine failed but was
	contained (home ownership repaired, installation continues vanilla).
	"""
	target = installation.target
	home_dir = target / 'home' / username
	repo_dir = home_dir / dotfiles.value

	info(f'Cloning {dotfiles.repository} into /home/{username}/ (as {username})...')

	# git may not be part of the base packages; install it before cloning.
	try:
		installation.pacman.strap('git')
	except SysCallError as err:
		warn(f'Could not install git for the dotfile deployment ({err}); continuing with vanilla Hyprland')
		_repair_home(installation, username)
		return False

	home_dir.mkdir(parents=True, exist_ok=True)

	try:
		installation.arch_chroot(clone_command(dotfiles, username), run_as=username)
	except SysCallError as err:
		warn(f'Dotfile clone failed ({err}); continuing with vanilla Hyprland')
		_repair_home(installation, username)
		return False

	if not repo_dir.is_dir():
		warn(f'Dotfile clone did not produce {repo_dir}; continuing with vanilla Hyprland')
		_repair_home(installation, username)
		return False

	plan = inspect_repository(repo_dir)

	if not plan.install_scripts:
		warn(
			f'{dotfiles.value} provides no installer script (inspected {_INSTALL_SCRIPT_NAMES}); continuing with vanilla Hyprland',
		)
		_repair_home(installation, username)
		return False

	if plan.required_packages:
		info(f'Appending dotfile prerequisite packages to the pacman transaction: {plan.required_packages}')
		try:
			installation.pacman.strap(plan.required_packages)
		except SysCallError as err:
			warn(f'Failed to install dotfile prerequisites ({err}); continuing with vanilla Hyprland')
			_repair_home(installation, username)
			return False

	failures = 0
	for script in plan.install_scripts:
		chroot_path = f'/home/{username}/{dotfiles.value}/{Path(script).name}'
		info(f'Running dotfile installer drop-privileged as {username}: {chroot_path}')

		try:
			installation.arch_chroot(run_installer_command(username, chroot_path), run_as=username, peek_output=True)
		except SysCallError as err:
			failures += 1
			warn(f'Dotfile installer {chroot_path} failed: {err}')

	# Ownership repair on success *and* failure.
	_repair_home(installation, username)

	if failures:
		warn(f'{dotfiles.value} finished with {failures} failed step(s); the desktop remains vanilla Hyprland')
		return False

	info(f'{dotfiles.value} deployed for user {username}')
	return True


def _repair_home(installation: Installer, username: str) -> None:
	home = f'/home/{username}'
	try:
		installation.chown(f'{username}:{username}', home, options=['-R'])
		debug(f'Repaired ownership of {home}')
	except SysCallError as err:
		warn(f'Failed to repair ownership of {home}: {err}')
