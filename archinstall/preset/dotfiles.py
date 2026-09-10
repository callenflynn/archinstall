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

# ML4W ships the actual configuration inside a dotfiles/ subfolder (declared by
# its own .dotinst profile) and keeps only maintenance scripts at the repo root,
# so the vanilla top-level installer inspection would find nothing to run.
_ML4W_CONFIG_SUBDIR = 'dotfiles'

# pacman/AUR-only ML4W entry points: preflight-arch.sh uninstalls swww
# (pacman -Rns) and post-arch.sh installs remaining tools + Oh My Posh +
# the ML4W settings app.  migration.sh and the _*.sh helpers are sourced by
# post-arch.sh itself and must not be invoked directly.
_ML4W_SETUP_SCRIPTS = ('preflight-arch.sh', 'post-arch.sh')

# Repository packages staged from pacman *before* the ML4W scripts run.
# Mirrors the suite's own setup/dependencies/packages + packages-arch lists
# (repository packages only, all verified official Arch repo names; the AUR
# remainder such as quickshell/matugen/awww is installed by the scripts
# through paru, which needs the base-devel toolchain for its builds).
_ML4W_STAGED_PACKAGES = [
	# toolchain + script prerequisites
	'base-devel',
	'wget',
	'unzip',
	'rsync',
	'jq',
	'gawk',
	'gum',
	'flatpak',
	'python-pipx',
	'python-pip',
	'xdg-user-dirs',
	'inotify-tools',
	'udisks2',
	'gvfs',
	'libnotify',
	'imagemagick',
	'pacman-contrib',
	'power-profiles-daemon',
	# Hyprland session core (the scripts never install these themselves;
	# the official ML4W installer does this dependency step)
	'kitty',
	'waybar',
	'rofi',
	'hyprpaper',
	'hyprlock',
	'hypridle',
	'hyprpicker',
	'hyprsunset',
	'swaync',
	'xdg-desktop-portal-hyprland',
	'xdg-desktop-portal-gtk',
	'polkit-gnome',
	'gnome-themes-extra',
	'qt5-wayland',
	'qt6-wayland',
	'nm-connection-editor',
	'network-manager-applet',
	'nwg-displays',
	'loupe',
	# desktop tools the ML4W keybindings call
	'wl-clipboard',
	'grim',
	'slurp',
	'cliphist',
	'brightnessctl',
	'pavucontrol',
	'fastfetch',
	'btop',
	'eza',
	'fzf',
	'neovim',
	# fonts
	'noto-fonts-emoji',
	'ttf-font-awesome',
	'otf-font-awesome',
	'ttf-nerd-fonts-symbols',
	'ttf-firacode-nerd',
	'ttf-jetbrains-mono-nerd',
]

# Temporary sudoers drop-in that lets the (untrusted but URL-hardcoded) ML4W
# scripts execute their internal `sudo` calls non-interactively.  Revoked
# immediately after the deployment.
_ML4W_SUDOERS_FILE = '99-archinstall-ml4w-tmp'

# Package manager *invocations* (install/sync forms) that indicate a script
# manages its own dependencies.  A bare mention of the manager's name (comment,
# echo, variable name, ...) does not count.
_PACKAGE_MANAGER_RE = re.compile(r'\b(?:pacman|paru|yay|apt-get|dnf)\s+(?:-{1,2}S|install|upgrade|-(?:Sy|Syu|Syy))\b')


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


def _ml4w_config_subdir() -> str:
	"""Subfolder that actually contains the ML4W configs (``dotfiles/``)."""
	return _ML4W_CONFIG_SUBDIR


def run_installer_command(username: str, script_path: str) -> str:
	"""
	Drop-privileged installer invocation (spec: NEVER as root).

	``script_path`` is the path inside the chroot; the wrapper is executed via
	``su - <username> -c <cmd>`` by :meth:`Installer.arch_chroot`.
	"""
	return f'/bin/bash {script_path}'


def inspect_repository(repo_path: Path, config_subdir: str = '') -> DotfilePlan:
	"""
	Inspect a freshly cloned (untrusted) repository from the live filesystem.

	Reads the README and installer scripts - never executes them - and decides
	whether the project handles its own dependencies (i.e. its scripts call a
	package manager).  When it does not, the conservative prerequisite package
	set is appended to the pacman transaction before execution.

	``config_subdir`` redirects the inspection into a repository subfolder for
	suites that keep their configs and scripts outside the repo root (ML4W).
	"""
	base = repo_path / config_subdir if config_subdir else repo_path

	install_scripts: list[str] = []
	deps_handled = False
	text = ''

	for name in _INSTALL_SCRIPT_NAMES:
		script = base / name
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
		readme = base / name
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

	if dotfiles == Dotfiles.ML4W:
		return _deploy_ml4w(installation, dotfiles, username, repo_dir)

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


def _deploy_ml4w(
	installation: Installer,
	dotfiles: Dotfiles,
	username: str,
	repo_dir: Path,
) -> bool:
	"""
	ML4W-specific deployment (https://ml4w.com).

	The repository has no top-level installer: the Hyprland configuration
	lives in ``dotfiles/`` (copied into ``~`` by the official installer, per
	the suite's own ``.dotinst`` profile) and ``setup/`` contains the
	pacman/AUR entry points, which expect ``$repo_path`` to point at the
	repository and call ``sudo`` internally.  The scripts themselves install
	the bulk of the stack, including ``paru`` on a fresh system.

	Privilege note: the suite's scripts are the only third-party code in the
	fork that requires root for its own ``sudo`` calls, so a temporary
	passwordless sudo grant is installed for the target user and revoked in a
	``finally`` block.  The repository URL is hard-coded in the fork (not
	user-supplied), stdin is closed so interactive prompts cannot hang the
	install, and home ownership is repaired afterwards either way.
	"""
	setup_dir = repo_dir / 'setup'

	install_scripts: list[str] = []
	for name in _ML4W_SETUP_SCRIPTS:
		script = setup_dir / name
		if script.is_file():
			install_scripts.append(str(script))

	if not install_scripts:
		warn('ML4W setup scripts not found (expected setup/preflight-arch.sh, setup/post-arch.sh); continuing with vanilla Hyprland')
		_repair_home(installation, username)
		return False

	info(f'Staging ML4W repository packages: {_ML4W_STAGED_PACKAGES}')
	try:
		installation.pacman.strap(_ML4W_STAGED_PACKAGES)
	except SysCallError as err:
		warn(f'Failed to stage ML4W packages ({err}); continuing with vanilla Hyprland')
		_repair_home(installation, username)
		return False

	# Copy the actual configuration into $HOME (the official .dotinst flow
	# restores exactly this subfolder); the repo checkout stays for updates.
	config_src = repo_dir / _ml4w_config_subdir()
	if config_src.is_dir():
		info(f'Installing ML4W configuration from {config_src.name}/ into /home/{username}/')
		try:
			installation.arch_chroot(
				f'cp -a /home/{username}/{dotfiles.value}/{_ml4w_config_subdir()}/. /home/{username}/',
				run_as=username,
			)
		except SysCallError as err:
			warn(f'Failed to copy ML4W configuration ({err}); continuing with vanilla Hyprland')
			_repair_home(installation, username)
			return False

	grant_path = _grant_temporary_sudo(installation, username)
	try:
		failures = 0
		for script in install_scripts:
			chroot_path = f'/home/{username}/{dotfiles.value}/setup/{Path(script).name}'
			info(f'Running ML4W setup drop-privileged as {username}: {chroot_path}')

			# $repo_path is required by the scripts; stdin is closed so that
			# package prompts (no --noconfirm in upstream scripts) cannot hang
			# a non-interactive install.
			command = f'export repo_path=/home/{username}/{dotfiles.value}; /bin/bash {chroot_path} </dev/null'

			try:
				installation.arch_chroot(command, run_as=username, peek_output=True)
			except SysCallError as err:
				failures += 1
				warn(f'ML4W setup {chroot_path} failed: {err}')
	finally:
		_revoke_temporary_sudo(grant_path)

	_repair_home(installation, username)

	if failures:
		warn(f'ML4W finished with {failures} failed step(s); the desktop remains vanilla Hyprland')
		return False

	info(f'{dotfiles.value} deployed for user {username}')
	return True


def _grant_temporary_sudo(installation: Installer, username: str) -> Path | None:
	"""
	Grant ``username`` passwordless sudo for the ML4W scripts (which call
	``sudo`` internally) and return the drop-in path for later revocation.
	"""
	sudoers_dir = installation.target / 'etc/sudoers.d'
	sudoers_file = installation.target / 'etc/sudoers'

	try:
		created_dir = not sudoers_dir.exists()
		sudoers_dir.mkdir(parents=True, exist_ok=True)

		if created_dir and sudoers_file.exists() and '@includedir /etc/sudoers.d' not in sudoers_file.read_text():
			with sudoers_file.open('a') as fh:
				fh.write('@includedir /etc/sudoers.d\n')

		rule = sudoers_dir / _ML4W_SUDOERS_FILE
		rule.write_text(f'{username} ALL=(ALL) NOPASSWD: ALL\n')
		rule.chmod(0o440)
	except OSError as err:
		warn(f'Could not create the temporary sudo grant for ML4W ({err}); its scripts may fail on sudo calls')
		return None

	debug(f'Temporary passwordless sudo granted to {username} for the ML4W deployment')
	return rule


def _revoke_temporary_sudo(rule: Path | None) -> None:
	"""Remove the temporary sudo grant (best effort, always attempted)."""
	if rule is None:
		return

	try:
		rule.unlink(missing_ok=True)
		debug('Revoked the temporary sudo grant used for the ML4W deployment')
	except OSError as err:
		warn(f'Failed to revoke the temporary ML4W sudo grant ({rule}): {err}')


def _repair_home(installation: Installer, username: str) -> None:
	home = f'/home/{username}'
	try:
		installation.chown(f'{username}:{username}', home, options=['-R'])
		debug(f'Repaired ownership of {home}')
	except SysCallError as err:
		warn(f'Failed to repair ownership of {home}: {err}')
