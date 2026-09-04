"""
Dynamic display manager selection (spec §1 MODE B + §4).

The recommendation mapping is pure and unit tested; the deployment helpers
operate on an :class:`~archinstall.lib.installer.Installer` inside the target
chroot.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from archinstall.default_profiles.profile import GreeterType
from archinstall.lib.command import SysCommand
from archinstall.lib.exceptions import ServiceException, SysCallError
from archinstall.lib.general.greetd import GREETER_CACHE_DIR, greetd_config, greetd_tmpfiles
from archinstall.lib.log import debug, info, warn
from archinstall.preset.options import Desktop

if TYPE_CHECKING:
	from archinstall.lib.installer import Installer

# Sessions that conflict with the selected display manager and therefore get
# disabled so exactly one login manager owns the display.
CONFLICTING_DM_SERVICES = ['sddm', 'gdm', 'lightdm', 'ly', 'cosmic-greeter', 'plasmalogin']

# Preferred session executables per desktop, checked in order against the
# session directories inside the target.
_SESSION_CANDIDATES: dict[Desktop, list[str]] = {
	Desktop.HYPRLAND: ['Hyprland'],
	Desktop.KDE_PLASMA: ['startplasma-wayland', 'startplasma-x11', 'plasma'],
	Desktop.GNOME: ['gnome-session', 'gnome'],
	Desktop.CINNAMON: ['cinnamon-session', 'cinnamon', 'cinnamon-session-cinnamon'],
	Desktop.XFCE: ['xfce-session', 'startxfce4'],
}


def recommended_greeter(desktop: Desktop) -> GreeterType | None:
	"""
	Map a desktop environment to its recommended display manager.

	* Hyprland       -> greetd + tuigreet
	* KDE Plasma     -> SDDM
	* GNOME          -> GDM
	* Cinnamon/XFCE  -> LightDM
	* Minimal CLI    -> None (no display manager)
	"""
	match desktop:
		case Desktop.HYPRLAND:
			return GreeterType.GreetdTuigreet
		case Desktop.KDE_PLASMA:
			return GreeterType.Sddm
		case Desktop.GNOME:
			return GreeterType.Gdm
		case Desktop.CINNAMON | Desktop.XFCE:
			return GreeterType.Lightdm
		case Desktop.MINIMAL_CLI:
			return None


def greeter_display_name(greeter: GreeterType) -> str:
	match greeter:
		case GreeterType.GreetdTuigreet:
			return 'greetd + tuigreet'
		case GreeterType.Sddm:
			return 'SDDM'
		case GreeterType.Gdm:
			return 'GDM'
		case GreeterType.Lightdm:
			return 'LightDM'
		case _:
			return str(greeter.value)


def session_candidates(desktop: Desktop) -> list[str]:
	return _SESSION_CANDIDATES.get(desktop, [])


def _session_dirs(installation: Installer) -> list[Path]:
	target = installation.target
	dirs = [target / 'usr/share/wayland-sessions', target / 'usr/share/xsessions']
	debug(f'Validating sessions against: {[str(d) for d in dirs]}')
	return dirs


def resolve_session_exec(installation: Installer, desktop: Desktop) -> str | None:
	"""
	Map the selected DE/WM to a validated session executable.

	Checks ``/usr/share/wayland-sessions`` then ``/usr/share/xsessions`` inside
	the target and returns the desktop-file name (``Hyprland``,
	``startplasma-wayland``, ``gnome-session``, ...) or the first configured
	candidate when nothing can be validated.
	"""
	for candidate in session_candidates(desktop):
		for session_dir in _session_dirs(installation):
			desktop_file = session_dir / f'{candidate}.desktop'
			if desktop_file.is_file():
				debug(f'Validated session executable: {candidate} ({desktop_file})')
				return candidate

	# The desktop package may name its session file differently (e.g. an
	# explicit Exec= line); fall back to the first known candidate so the
	# greeter still boots instead of failing hard.
	if candidates := session_candidates(desktop):
		warn(
			f'Could not validate a session file for {desktop.value} inside the target; using {candidates[0]} as the greeter session command.',
		)
		return candidates[0]

	return None


def deploy_greetd(
	installation: Installer,
	desktop: Desktop,
	user: str = 'greeter',
) -> None:
	"""
	Deploy greetd + tuigreet inside the target (spec §4 step 3):

	1. Resolve + validate the session executable.
	2. Write ``/etc/greetd/config.toml`` with the tuigreet command.
	3. Ensure the ``greeter`` user exists and owns ``/var/cache/tuigreet``.
	4. Enable ``greetd.service`` and disable conflicting DM services.
	"""
	session_exec = resolve_session_exec(installation, desktop)
	if session_exec is None:
		warn(f'No session executable could be resolved for {desktop.value}; greetd will use the default')
		session_exec = 'Hyprland'

	config_path = installation.target / 'etc/greetd/config.toml'
	config_path.parent.mkdir(parents=True, exist_ok=True)
	config_path.write_text(greetd_config(session_exec))

	tmpfiles_path = installation.target / 'etc/tmpfiles.d/greetd-tuigreet.conf'
	tmpfiles_path.parent.mkdir(parents=True, exist_ok=True)
	tmpfiles_path.write_text(greetd_tmpfiles())

	# Ensure the greeter user + cache directory exist.  greetd ships a sysusers
	# fragment in recent versions; creating the user defensively is idempotent.
	try:
		SysCommand(f'arch-chroot {installation.target} getent passwd {user}')
	except SysCallError:
		info(f'Creating greeter system user "{user}" inside the target')
		try:
			SysCommand(f'arch-chroot {installation.target} useradd --system --no-create-home --shell /bin/false {user}')
		except SysCallError as err:
			warn(f'Could not create the greeter user: {err}')

	cache_path = installation.target / GREETER_CACHE_DIR.lstrip('/')
	cache_path.mkdir(parents=True, exist_ok=True)
	installation.chown(f'{user}:{user}', GREETER_CACHE_DIR)
	cache_path.chmod(0o755)

	for service in CONFLICTING_DM_SERVICES:
		try:
			installation.disable_service(service)
		except ServiceException:
			debug(f'Display manager {service} could not be disabled; continuing')

	installation.enable_service('greetd')
	try:
		installation.disable_service('getty@tty1')
	except ServiceException:
		debug('getty@tty1 could not be disabled; continuing')

	info(f'greetd + tuigreet configured for {desktop.value} (session: {session_exec})')
