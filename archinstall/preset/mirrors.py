"""
Best-effort automatic mirror ranking via ``reflector`` (spec MODE A).

Reflector may be missing or fail on minimal live environments; per the
resilience spec the failure path is non-fatal and simply keeps the standard
ranked Arch ISO mirrorlist (i.e. no custom mirror configuration is applied).

The parser is pure and unit tested; ranking runs only inside the interactive
flow and is best-effort by design.
"""

import tempfile
from pathlib import Path

from archinstall.lib.command import SysCommand
from archinstall.lib.log import info, warn
from archinstall.lib.models.mirrors import CustomServer, MirrorConfiguration


def parse_reflector_mirrorlist(content: str) -> list[str]:
	"""
	Extract ``Server = <url>`` lines from a reflector-generated mirrorlist.
	"""
	servers: list[str] = []

	for line in content.splitlines():
		line = line.strip()
		if line.startswith('Server = '):
			server = line.removeprefix('Server = ').strip()
			if server:
				servers.append(server)

	return servers


def rank_mirrors_with_reflector() -> MirrorConfiguration | None:
	"""
	Auto-rank the nearest Arch mirrors with reflector.

	Returns a mirror configuration carrying the ranked servers, or ``None``
	when ranking failed - in which case the installer keeps the standard
	mirrorlist (already ranked by the ISO's reflector service when present).
	"""
	try:
		with tempfile.NamedTemporaryFile(mode='r+', suffix='.mirrorlist', delete=False) as tmp:
			tmp_path = Path(tmp.name)
	except OSError as err:
		warn(f'Could not create a temporary mirrorlist for reflector: {err}')
		return None

	try:
		# No --country filter: ranking happens purely on measured latency/rate
		# so 'nearest mirrors' is decided by real network conditions.
		SysCommand(
			f'reflector --protocol https --latest 15 --sort rate --save {tmp_path}',
			peek_output=True,
		)
		servers = parse_reflector_mirrorlist(tmp_path.read_text())
	finally:
		tmp_path.unlink(missing_ok=True)

	if not servers:
		warn('Reflector produced no ranked mirrors; falling back to the standard Arch ISO mirrorlist')
		return None

	info(f'Reflector ranked {len(servers)} mirrors')

	return MirrorConfiguration(custom_servers=[CustomServer(url) for url in servers])
