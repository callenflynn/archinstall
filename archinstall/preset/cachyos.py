"""
CachyOS repository integration (spec §3 and §4).

Repository facts were verified against the official CachyOS sources:

* Wiki "Optimized Repositories" (https://wiki.cachyos.org/features/optimized_repos/):
``[cachyos-<level>]`` / ``[cachyos-core-<level>]`` / ``[cachyos-extra-<level>]``
stanzas must be placed *above* ``[core]``/``[extra]``; each level Includes its
own mirrorlist, and x86-64-v4 and znver4 share ``cachyos-v4-mirrorlist``.
* The official repository installer
(https://github.com/CachyOS/cachyos-repo-add-script/blob/develop/cachyos-repo.sh)
imports and locally signs master key ``F3B607488DB35A47`` and installs the
``cachyos-keyring`` / ``cachyos-mirrorlist`` (plus per-level mirrorlist)
packages natively.

The pure helpers in this module (level classification, stanza generation,
pacman.conf injection, mirrorlist rendering) are unit tested; everything that
touches the live system is layered on top of those primitives.
"""

import re
import shlex
from pathlib import Path
from typing import Final

from archinstall.lib.command import SysCommand
from archinstall.lib.exceptions import SysCallError
from archinstall.lib.log import debug, info, warn
from archinstall.preset.options import CachyosLevel

# Verified master signing key of the CachyOS repositories
CACHYOS_MASTER_KEY_ID: Final = 'F3B607488DB35A47'
CACHYOS_KEYSERVER: Final = 'keyserver.ubuntu.com'
CACHYOS_MIRROR_DIR: Final = '/etc/pacman.d'

# Packages that provision the keyring + mirrorlists inside the target system
KEYRING_AND_MIRRORLIST_PACKAGES: Final = ['cachyos-keyring', 'cachyos-mirrorlist']

# Fallback servers for the (temporary) live-environment mirrorlist.  The
# installed system replaces these with the official mirrorlist package files
# that are strapped in together with the base system.
CACHYOS_GEO_MIRRORS: Final = [
	'https://geo.cachyos.org/repo/$repo/$arch',
	'https://mirror.cachyos.org/repo/$repo/$arch',
]

# Repository levels are ordered from most to least specialized.
ISA_LEVELS: Final = ('znver4', 'v4', 'v3')


class CachyosLevelError(ValueError):
	"""Raised for invalid ISA levels passed to pure builders."""


class CachyosSetupError(RuntimeError):
	"""
	Critical failure during CachyOS repository setup.

	Per the fork spec (section 5) GPG key import failures are critical and
	stop the installation with a clear error message.
	"""


def normalize_level(level: CachyosLevel | str | None) -> str | None:
	"""
	Map the fork option vocabulary onto the repository helpers.

	``CachyosLevel.GENERIC`` (or ``None``) means the plain ``[cachyos]``
	repository without an ISA suffix.
	"""
	if level is None or level == CachyosLevel.GENERIC:
		return None
	return CachyosLevel(level).value


def detect_isa_level(
	glibc_levels: set[str],
	march_native: str | None,
	vendor_id: str | None,
) -> str | None:
	"""
	Map host CPU capabilities onto the CachyOS ISA repository level.

	Mirrors the official repo script (``/lib/ld-linux-x86-64.so.2 --help`` +
	``gcc -march=native``) and returns ``None`` (= use the generic
	``[cachyos]`` repository) for anything ambiguous, which is the specified
	fallback behavior.

	Note: Intel hybrid CPUs (Alder Lake et al.) report x86-64-v4 support from
	glibc even though AVX-512 is fused off; the CachyOS wiki recommends
	treating them as v3.  We keep the official script's behavior (glibc wins)
	because there is no reliable way to distinguish fused-off hybrids at
	runtime, and document the caveat here.
	"""
	supported = {level for level in glibc_levels if level in ('v2', 'v3', 'v4')}

	if 'v4' in supported:
		if march_native:
			normalized = march_native.lower()

			if normalized.startswith('znver'):
				return 'znver4'

			# gcc confirming a non-znver v4 march (e.g. x86-64-v4)
			if normalized in ('x86-64-v4',):
				return 'v4'

		# gcc is unavailable (plain Arch ISO has no gcc).  znver4 requires an
		# AMD Zen4+ CPU: vendor + v4 level support is a conservative proxy, but
		# Intel also reports v4 here, so only return v4, never znver4, without
		# a positive gcc signal.  This intentionally avoids over-tuning Intel
		# CPUs and leaves znver4 detection to the explicit gcc path above.
		if vendor_id and 'AuthenticAMD' not in vendor_id:
			return 'v4'

		# AMD v4 without gcc is ambiguous (could be generic v4), fall through to v3
		debug('AMD v4 CPU detected without gcc; treating as x86-64-v3 (ambiguity fallback)')
		return 'v3'

	if 'v3' in supported:
		return 'v3'

	debug('CPU ISA level ambiguous (v1/v2 or undetectable); falling back to generic [cachyos]')
	return None


def read_glibc_supported_levels(ld_path: str = '/lib/ld-linux-x86-64.so.2') -> set[str]:
	"""Return the x86-64 microarchitecture levels glibc reports as supported."""
	try:
		output = SysCommand(f'{ld_path} --help').decode()
	except SysCallError:
		return set()

	levels = set()
	for line in output.splitlines():
		match = re.search(r'x86-64-(v\d) \(supported', line)
		if match:
			levels.add(match.group(1))
	return levels


def read_march_native() -> str | None:
	"""
	Ask gcc for ``-march=native`` when available.

	Returns ``None`` when gcc is missing (then :func:`detect_isa_level` falls
	back to glibc-only logic).
	"""
	try:
		output = SysCommand('gcc -march=native -Q --help=target').decode()
	except SysCallError:
		return None
	except OSError:
		return None

	for line in output.splitlines():
		match = re.search(r'-march=\s*(\S+)', line)
		if match:
			return match.group(1).strip()
	return None


def read_cpu_vendor() -> str | None:
	"""Read ``vendor_id`` from /proc/cpuinfo (first processor block)."""
	try:
		content = Path('/proc/cpuinfo').read_text()
	except OSError:
		return None

	for line in content.splitlines():
		if line.startswith('vendor_id'):
			_, _, value = line.partition(':')
			return value.strip()
	return None


def detected_level() -> str | None:
	"""Detect the ISA level for the *running* host with safe fallbacks."""
	return detect_isa_level(read_glibc_supported_levels(), read_march_native(), read_cpu_vendor())


def mirrorlist_name(level: str | None) -> str:
	"""
	Mirrorlist file name referenced by the Include= line for a level.

	Generic ``[cachyos]`` uses ``cachyos-mirrorlist``; v3 uses
	``cachyos-v3-mirrorlist``; v4 and znver4 share ``cachyos-v4-mirrorlist``.
	"""
	match level:
		case None:
			return 'cachyos-mirrorlist'
		case 'v3':
			return 'cachyos-v3-mirrorlist'
		case 'v4' | 'znver4':
			return 'cachyos-v4-mirrorlist'
		case _:
			raise CachyosLevelError(f'Unknown CachyOS ISA level: {level}')


def repo_stanza(level: str | None) -> str:
	"""
	Render the pacman.conf stanza block for a given ISA level.

	The block contains the level-specific repositories followed by the plain
	``[cachyos]`` repository.  The caller places it *before* ``[core]``.
	"""
	if level is None:
		sections = ['cachyos']
	else:
		sections = [f'cachyos-{level}', f'cachyos-core-{level}', f'cachyos-extra-{level}', 'cachyos']

	lines: list[str] = ['# cachyos repositories']
	for section in sections:
		lines.append(f'[{section}]')
		lines.append(f'Include = {CACHYOS_MIRROR_DIR}/{mirrorlist_name(level)}')

	return '\n'.join(lines) + '\n'


def mirrorlist_content(level: str | None) -> str:
	"""Minimal mirrorlist used on the live medium until the pkg-provided one lands."""
	lines = ['## CachyOS mirror (live environment, temporary)', '## World']
	lines.extend(f'Server = {server}' for server in CACHYOS_GEO_MIRRORS)
	return '\n'.join(lines) + '\n'


def inject_before_core(pacman_conf: str, level: str | None) -> str:
	"""
	Inject the CachyOS stanzas at the very top of ``/etc/pacman.conf``,
	preceding ``[core]`` (and therefore also ``[extra]``).

	If the repositories are already present (e.g. an ISO that ships them or a
	previous dry-run) the configuration is left untouched so the operation is
	idempotent.
	"""
	if '[cachyos]' in pacman_conf:
		debug('cachyos repositories already present in pacman.conf; skipping injection')
		return pacman_conf

	core_match = re.search(r'^\[core\]', pacman_conf, flags=re.MULTILINE)
	if core_match is None:
		raise CachyosSetupError('pacman.conf does not contain a [core] section; refusing to inject repositories')

	insert_at = core_match.start()
	return pacman_conf[:insert_at] + repo_stanza(level) + pacman_conf[insert_at:]


def mirrorlist_packages_for_level(level: CachyosLevel | str | None) -> list[str]:
	"""Keyring + mirrorlist packages that must ride the base pacstrap transaction."""
	level = normalize_level(level)
	packages = list(KEYRING_AND_MIRRORLIST_PACKAGES)

	match level:
		case 'v3':
			packages.append('cachyos-v3-mirrorlist')
		case 'v4' | 'znver4':
			packages.append('cachyos-v4-mirrorlist')
		case None:
			pass
		case _:
			raise CachyosLevelError(f'Unknown CachyOS ISA level: {level}')

	return packages


def _write(path: Path, content: str) -> None:
	path.write_text(content)
	debug(f'Wrote {path}')


def import_and_sign_key(keyserver: str = CACHYOS_KEYSERVER) -> None:
	"""
	Import the CachyOS master key into the *current* keyring and locally sign
	it so pacman accepts signatures from the CachyOS repositories.

	This is a critical step: pacman refuses to download from unsigned repos,
	so a failure here is raised as :class:`CachyosSetupError`.
	"""
	info('Importing CachyOS repository signing key...')

	try:
		SysCommand(f'pacman-key --recv-keys {CACHYOS_MASTER_KEY_ID} --keyserver {keyserver}', peek_output=True)
		SysCommand(f'pacman-key --lsign-key {CACHYOS_MASTER_KEY_ID}', peek_output=True)
	except SysCallError as err:
		raise CachyosSetupError(
			f'Failed to import/locally-sign the CachyOS GPG key {CACHYOS_MASTER_KEY_ID}. Reason: {err}. Aborting to avoid an untrusted repository setup.',
		) from err

	info('CachyOS repository signing key imported and locally signed')


def prepare_live_environment(level: str | None) -> None:
	"""
	Enable the CachyOS repositories on the live medium *before* the base
	pacstrap so the single base transaction can already pull from them.

	Only the live ``/etc/pacman.conf`` + mirrorlists are mutated here; the
	target system receives its copy through ``pacman_conf.persist()`` during
	:meth:`Installer.minimal_installation`.
	"""
	level = normalize_level(level)
	if level is None:
		return

	import_and_sign_key()

	pacman_conf = Path('/etc/pacman.conf')
	conf = inject_before_core(pacman_conf.read_text(), level)
	pacman_conf.write_text(conf)

	for level_name in (None, level):
		mirror_path = Path(CACHYOS_MIRROR_DIR) / mirrorlist_name(level_name)
		_write(mirror_path, mirrorlist_content(level_name))

	info(f'CachyOS repositories ({level or "generic"}) enabled on the live medium')


def _chroot(installation: object, command: str, peek: bool = False) -> None:
	from archinstall.lib.installer import Installer

	assert isinstance(installation, Installer)
	installation.arch_chroot(command, peek_output=peek)


def synchronize_target(installation: object, level: str | None) -> None:
	"""
	Run a full synchronized system upgrade inside the target chroot.

	The installed base already contains ``cachyos-keyring``/``cachyos-mirrorlist``
	(strapped in the same transaction as the base packages), so the chroot
	keyring already trusts the CachyOS signature and this is a plain
	``pacman -Syu`` - never a standalone ``pacman -Sy``.
	"""
	level = normalize_level(level)
	if level is None:
		return

	info('Performing synchronized system upgrade (pacman -Syu) inside the target...')

	try:
		_chroot(installation, 'pacman -Syu --noconfirm', peek=True)
	except SysCallError as err:
		raise CachyosSetupError(
			f'Synchronized system upgrade failed inside the target chroot: {err}. Aborting to avoid leaving the system in a partially upgraded state.',
		) from err

	# The upgrade may have replaced kernel/initramfs packages; regenerate
	# before the bootloader step runs.
	try:
		_chroot(installation, 'mkinitcpio -P', peek=True)
	except SysCallError as err:
		warn(f'initramfs regeneration after synchronized upgrade failed: {err}')


def ensure_target_keyring_trust(installation: object) -> None:
	"""
	Re-establish CachyOS trust inside the installed target.

	Every pacstrap call (``-K``) re-initializes the target keyring, wiping any
	additional trust added earlier.  The cachyos-keyring package ships its
	keyring material so ``pacman-key --populate cachyos`` restores it offline;
	when that is not sufficient we fall back to keyserver import + local sign.

	This step must run after the *last* package transaction.
	"""
	from archinstall.lib.installer import Installer

	assert isinstance(installation, Installer)

	try:
		_chroot(installation, 'pacman-key --populate cachyos archlinux')
		info('Target CachyOS keyring trust restored (pacman-key --populate)')
	except SysCallError as err:
		debug(f'pacman-key --populate cachyos failed: {err}; falling back to keyserver import')

		try:
			_chroot(
				installation,
				f'pacman-key --recv-keys {CACHYOS_MASTER_KEY_ID} --keyserver {shlex.quote(CACHYOS_KEYSERVER)}',
			)
			_chroot(installation, f'pacman-key --lsign-key {CACHYOS_MASTER_KEY_ID}')
			info('Target CachyOS keyring trust restored (keyserver import)')
		except SysCallError as exc:
			raise CachyosSetupError(
				f'{exc} Could not restore CachyOS keyring trust inside the installed system. '
				'The system may still be usable but CachyOS repositories will not verify '
				'until the keyring is fixed manually.',
			) from exc


def install_paru_guarded(installation: object) -> None:
	"""Install the paru AUR helper if the repos provide it; failure is non-fatal."""
	from archinstall.lib.installer import Installer

	assert isinstance(installation, Installer)

	try:
		installation.pacman.strap('paru')
		info('Installed paru (AUR helper)')
	except SysCallError as err:
		warn(f'Failed to install paru from the repositories: {err}. Continuing without an AUR helper.')
