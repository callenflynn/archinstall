"""
Dynamic GPU detection and driver package selection.

Detection deliberately parses ``lspci`` output so the logic is unit-testable
and the live probe (see :func:`probe_pci_devices`) stays a thin wrapper.

Driver selection rules (CachyOS / Arch packages):

* NVIDIA Turing and newer -> ``nvidia-open-dkms`` family (+ ``nvidia-utils``,
``lib32-nvidia-utils``, ``egl-wayland``, ``libva-nvidia-driver``).
* NVIDIA pre-Turing -> nouveau (open) fallback, matching the fact that the
proprietary legacy driver is not available from the repos anymore.
* AMD -> ``mesa`` + ``lib32-mesa`` + ``xf86-video-amdgpu`` + ``vulkan-radeon``
+ ``lib32-vulkan-radeon``.
* Intel -> ``mesa`` + ``lib32-mesa`` + ``vulkan-intel`` + ``intel-media-driver``.
* Hybrid (dual GPU) -> union of both sets plus ``envycontrol``.
* Anything unclassified -> plain ``mesa`` (open-source fallback).
"""

import re
from dataclasses import dataclass
from enum import Enum

from archinstall.lib.command import SysCommand
from archinstall.lib.exceptions import SysCallError
from archinstall.lib.log import debug, info, warn
from archinstall.preset.options import GpuPlan

# NVIDIA architectures that are supported by the open kernel module:
# Turing (sm_75+), Ampere (sm_86), Ada (sm_89) and Blackwell (sm_120).
_TURING_PLUS_MARKERS = (
	'rtx a',
	'rtx 2',
	'rtx 3',
	'rtx 4',
	'rtx 5',
	'gtx 16',
	'turing',
	'quadro rtx',
	'a100',
	'a2000',
	'a3000',
	'a4000',
	'a5000',
	'a6000',
	'a800',
	'l4',
	'l40',
	'l40s',
	'h100',
	'blackwell',
	'b100',
	'b200',
	'gb200',
	'rtx pro',
	'rtx 6000 ada',
	'rtx 4000 ada',
	'rtx 5000 ada',
	'rtx 2000 ada',
)


class Vendor(Enum):
	NVIDIA = 'nvidia'
	AMD = 'amd'
	INTEL = 'intel'
	UNKNOWN = 'unknown'
	VM = 'vm'


@dataclass(frozen=True)
class GpuDevice:
	"""A parsed display controller from a single ``lspci`` line."""

	identifier: str
	vendor: Vendor
	bus: str = ''
	pci_line: str = ''


def classify_vendor(identifier: str) -> Vendor:
	lower = identifier.lower()

	if any(marker in lower for marker in ('nvidia', 'quadro', 'tesla', 'geforce')):
		return Vendor.NVIDIA

	# 'ati' needs word boundaries: bare substring matching would fire on
	# every "corporATION" in a vendor string.
	if 'advanced micro devices' in lower or 'amd' in lower or 'radeon' in lower or re.search(r'(?<![a-z])ati(?![a-z])', lower) is not None:
		return Vendor.AMD

	if 'intel corporation' in lower or 'intel' in lower:
		return Vendor.INTEL

	if any(marker in lower for marker in ('vmware', 'qxl', 'virtio', 'cirrus', 'bochs', 'microsoft basic')):
		return Vendor.VM

	return Vendor.UNKNOWN


def parse_pci_lines(pci_lines: list[str]) -> list[GpuDevice]:
	"""
	Parse raw ``lspci`` output into :class:`GpuDevice` entries.

	Only VGA / 3D controllers are considered; sound cards and USB bridges
	that mention a vendor name must not influence the driver selection.
	"""
	devices: list[GpuDevice] = []

	for line in pci_lines:
		if not any(tag in line for tag in (' VGA ', ' 3D ')):
			continue

		if ': ' not in line:
			continue

		bus_part, identifier = line.split(': ', 1)
		identifier = identifier.strip()

		devices.append(
			GpuDevice(
				identifier=identifier,
				vendor=classify_vendor(identifier),
				bus=bus_part,
				pci_line=line,
			),
		)

	return devices


def is_turing_plus(identifier: str) -> bool:
	lower = identifier.lower()
	return any(marker in lower for marker in _TURING_PLUS_MARKERS)


def nvidia_generation(identifier: str) -> str | None:
	"""
	Classify a NVIDIA device name.

	Returns ``'turing_plus'``, ``'pre_turing'`` or ``None`` when the device
	name carries no generation information.
	"""
	lower = identifier.lower()

	if is_turing_plus(lower):
		return 'turing_plus'

	# Any NVIDIA-branded name (vendor line "NVIDIA Corporation ..." or the
	# consumer/Pro naming without the vendor word) that lacks a Turing+
	# marker is a pre-Turing card.
	if any(marker in lower for marker in ('nvidia', 'geforce', 'quadro', 'tesla')):
		return 'pre_turing'

	return None


def gpu_plan(devices: list[GpuDevice]) -> tuple[GpuPlan, list[str]]:
	"""
	Resolve the driver plan and concrete package list for the detected GPUs.

	Hybrid configurations install the union of both driver sets together with
	``envycontrol`` (prime-run style GPU switching).  Any unclassified device
	falls back to generic open-source ``mesa``.
	"""
	if not devices:
		return GpuPlan.GENERIC_MESA, ['mesa']

	vendors = {device.vendor for device in devices}

	if Vendor.VM in vendors:
		return GpuPlan.VM, ['mesa']

	nvidia_devices = [d for d in devices if d.vendor == Vendor.NVIDIA]
	non_nvidia = [d for d in devices if d.vendor in (Vendor.AMD, Vendor.INTEL)]

	if nvidia_devices and non_nvidia:
		_, nvidia_pkgs = _nvidia_packages(nvidia_devices)
		_, other_pkgs = gpu_plan([non_nvidia[0]])

		packages = sorted(set(nvidia_pkgs + other_pkgs + ['envycontrol']))
		return GpuPlan.HYBRID, packages

	if Vendor.NVIDIA in vendors:
		plan, packages = _nvidia_packages(nvidia_devices)
		return plan, packages

	if Vendor.AMD in vendors and len(vendors) == 1:
		return GpuPlan.AMD, [
			'mesa',
			'lib32-mesa',
			'xf86-video-amdgpu',
			'vulkan-radeon',
			'lib32-vulkan-radeon',
		]

	if Vendor.INTEL in vendors and len(vendors) == 1:
		return GpuPlan.INTEL, [
			'mesa',
			'lib32-mesa',
			'vulkan-intel',
			'intel-media-driver',
		]

	# Mixed AMD + Intel (common iGPU + dGPU) without NVIDIA: both are open
	# source, installing the union keeps everything accelerated.
	if Vendor.AMD in vendors and Vendor.INTEL in vendors:
		_, amd_pkgs = gpu_plan([GpuDevice('amd', Vendor.AMD)])
		_, intel_pkgs = gpu_plan([GpuDevice('intel', Vendor.INTEL)])
		return GpuPlan.HYBRID, sorted(set(amd_pkgs + intel_pkgs))

	debug(f'Unclassified graphics devices: {[d.identifier for d in devices]}')
	return GpuPlan.GENERIC_MESA, ['mesa']


def _nvidia_packages(nvidia_devices: list[GpuDevice]) -> tuple[GpuPlan, list[str]]:
	if all(nvidia_generation(d.identifier) == 'turing_plus' for d in nvidia_devices):
		packages = [
			'nvidia-open-dkms',
			'dkms',
			'nvidia-utils',
			'lib32-nvidia-utils',
			'egl-wayland',
			'libva-nvidia-driver',
		]
		return GpuPlan.NVIDIA_OPEN, packages

	warn(
		'Detected NVIDIA GPUs without Turing+ support markers; falling back to the open nouveau driver stack.',
	)

	# Open-source nouveau path: matches GfxDriver.NvidiaOpenSource
	return GpuPlan.NVIDIA_LEGACY, [
		'mesa',
		'xf86-video-nouveau',
		'vulkan-nouveau',
		'lib32-mesa',
	]


def probe_pci_devices() -> list[GpuDevice]:
	"""
	Live hardware probe.  Failure to run ``lspci`` degrades gracefully to an
	empty list, which callers map to the generic mesa fallback.
	"""
	try:
		output = SysCommand('lspci').decode()
	except SysCallError as err:
		warn(f'GPU detection failed (lspci): {err}; falling back to generic mesa drivers')
		return []

	lines = [line for line in output.splitlines() if line.strip()]
	devices = parse_pci_lines(lines)
	info(f'Detected graphics devices: {[d.identifier for d in devices]}')
	return devices
