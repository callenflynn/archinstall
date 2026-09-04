"""
greetd + tuigreet configuration helpers (shared by profiles and the preset).

Writing ``/etc/greetd/config.toml`` requires a validated session executable so
the greeter can launch the desktop session directly (tuigreet ``--cmd``).
"""

from typing import Final

# Fallback session used when the config is written before the desktop profile
# is resolvable (profiles handler default).  The preset flow overwrites the
# file with a validated session executable during finalize.
DEFAULT_SESSION_EXEC: Final = 'Hyprland'

# The greeter needs a persistent cache directory owned by the ``greeter`` user
# (tuigreet stores session history / wallpaper data there).
GREETER_CACHE_DIR: Final = '/var/cache/tuigreet'


def greetd_config(session_exec: str = DEFAULT_SESSION_EXEC) -> str:
	"""
	Render ``/etc/greetd/config.toml`` for tuigreet.

	``session_exec`` is the validated desktop session executable passed to
	``tuigreet --cmd`` so the greeter can start the session without an extra
	shell wrapper.
	"""
	return f'[terminal]\nvt = 1\n\n[default_session]\ncommand = "tuigreet --time --asterisks --user-menu --cmd {session_exec}"\nuser = "greeter"\n'


def greetd_tmpfiles() -> str:
	"""
	Return a tmpfiles.d snippet that keeps the greeter cache directory present
	and owned by the ``greeter`` user across reboots.
	"""
	return f'# Path                    Mode User    Group   Age Argument\nd {GREETER_CACHE_DIR}   0755 greeter greeter -\n'
