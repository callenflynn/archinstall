import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import parted
import pytest

# Compatibility shim for CI/dev hosts with libparted < 3.6: archinstall's model
# layer reads parted constants at import time (XBOOTLDR -> PARTITION_BLS_BOOT,
# ESP -> PARTITION_ESP, LINUX_HOME -> PARTITION_LINUX_HOME) that were only
# added in libparted 3.6.  Arch ships libparted 3.6+, where they all exist, so
# this is a no-op there; on older hosts we synthesize them with the canonical
# sequential PedPartitionFlag values (ESP=16, BLS_BOOT=17, LINUX_HOME=18) so the
# model can import and tests can construct flags.  The pyparted C module and the
# parted python wrapper both need the names.
_PARTED_MISSING = {
	'PARTITION_ESP': 16,
	'PARTITION_BLS_BOOT': 17,
	'PARTITION_LINUX_HOME': 18,
}
for _name, _value in _PARTED_MISSING.items():
	if not hasattr(parted, _name):
		setattr(parted, _name, _value)
	try:
		import _ped as _ped_module  # type: ignore[import-not-found]
	except ImportError:
		_ped_module = None
	if _ped_module is not None and not hasattr(_ped_module, _name):
		setattr(_ped_module, _name, _value)


# Compatibility shim for dev hosts whose util-linux < 2.38 cannot emit every
# column archinstall requests from lsblk (e.g. `partn` on Ubuntu 22.04).  The
# columns are probed once per test session and LsblkInfo.fields() is narrowed
# to the intersection.  Arch's CI container ships a current util-linux where
# all columns exist, so this is a no-op there.  All LsblkInfo fields are
# optional in the model, so omitting unsupported columns keeps parsing intact.
_FIELDS_NARROWED: dict[str, bool] = {'done': False}


def _lsblk_supported_columns() -> set[str]:
	from archinstall.lib.models.device import LsblkInfo

	supported: set[str] = set()
	for column in LsblkInfo.fields():
		probe = subprocess.run(
			['lsblk', '--output', column],
			capture_output=True,
			check=False,
		)
		if probe.returncode == 0:
			supported.add(column)

	return supported


def _narrow_lsblk_fields() -> None:
	from archinstall.lib.models.device import LsblkInfo

	if _FIELDS_NARROWED['done']:
		return
	_FIELDS_NARROWED['done'] = True

	requested = LsblkInfo.fields()
	supported = _lsblk_supported_columns()
	if supported >= set(requested):
		return

	narrowed = [column for column in requested if column in supported]
	if narrowed != requested:
		LsblkInfo.fields = classmethod(lambda cls: narrowed)  # type: ignore[assignment]


@pytest.fixture(scope='session', autouse=True)
def _lsblk_compat(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
	"""Session-wide environment accommodation (no-op on current Arch hosts).

	Works around two old-util-linux (e.g. Ubuntu 22.04) host quirks: ``partn``
	is only emitted by util-linux >= 2.38, so unsupported columns are dropped
	from ``LsblkInfo.fields()``; and an empty ``/proc/swaps`` makes old lsblk
	warn on stderr (archinstall merges stderr into stdout, which would break
	JSON parsing), so ``lsblk`` is shadowed with a wrapper that silences
	stderr.  On Arch (project CI) util-linux is current, so the shims change
	nothing.
	"""
	_narrow_lsblk_fields()

	lsblk_binary = shutil.which('lsblk')
	if lsblk_binary is None:
		yield
		return

	shim_dir = tmp_path_factory.mktemp('lsblk-shim')
	wrapper = shim_dir / 'lsblk'
	wrapper.write_text(f'#!/bin/sh\nexec {lsblk_binary} "$@" 2>/dev/null\n')
	wrapper.chmod(0o755)

	old_path = os.environ.get('PATH', '')
	os.environ['PATH'] = f'{shim_dir}{os.pathsep}{old_path}'
	yield
	if old_path:
		os.environ['PATH'] = old_path
	else:
		os.environ.pop('PATH', None)


@pytest.fixture(scope='session')
def config_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'test_config.json'


@pytest.fixture(scope='session')
def example_config_fixture() -> Path:
	return Path(__file__).parent.parent / 'examples' / 'config-sample.json'


@pytest.fixture(scope='session')
def example_creds_fixture() -> Path:
	return Path(__file__).parent.parent / 'examples' / 'creds-sample.json'


@pytest.fixture(scope='session')
def btrfs_config_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'test_config_btrfs.json'


@pytest.fixture(scope='session')
def creds_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'test_creds.json'


@pytest.fixture(scope='session')
def encrypted_creds_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'test_encrypted_creds.json'


@pytest.fixture(scope='session')
def deprecated_creds_config() -> Path:
	return Path(__file__).parent / 'data' / 'test_deprecated_creds_config.json'


@pytest.fixture(scope='session')
def deprecated_mirror_config() -> Path:
	return Path(__file__).parent / 'data' / 'test_deprecated_mirror_config.json'


@pytest.fixture(scope='session')
def deprecated_audio_config() -> Path:
	return Path(__file__).parent / 'data' / 'test_deprecated_audio_config.json'


@pytest.fixture(scope='session')
def mirrorlist_no_country_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'mirrorlists' / 'test_no_country'


@pytest.fixture(scope='session')
def mirrorlist_with_country_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'mirrorlists' / 'test_with_country'


@pytest.fixture(scope='session')
def mirrorlist_multiple_countries_fixture() -> Path:
	return Path(__file__).parent / 'data' / 'mirrorlists' / 'test_multiple_countries'
