.. _fork.hardware:

Dynamic GPU detection & driver selection
========================================

The installer probes the host hardware (``lspci`` output, VGA and 3D
controllers only) and resolves a driver plan plus a concrete package list
before the desktop profile is installed.  Detection is best-effort: any
failure falls back to the generic open-source ``mesa`` stack.

Driver selection rules
----------------------

.. list-table::
   :widths: 22 78
   :header-rows: 1

   * - Detected hardware
     - Installed packages
   * - NVIDIA Turing and newer (RTX 2xxx+, GTX 16xx, RTX Axxx, Ada/Blackwell)
     - ``nvidia-open-dkms``, ``dkms``, ``nvidia-utils``, ``lib32-nvidia-utils``,
       ``egl-wayland``, ``libva-nvidia-driver``
   * - NVIDIA pre-Turing
     - open-source ``nouveau`` stack: ``mesa``, ``xf86-video-nouveau``,
       ``vulkan-nouveau``, ``lib32-mesa``
   * - AMD
     - ``mesa``, ``lib32-mesa``, ``xf86-video-amdgpu``, ``vulkan-radeon``,
       ``lib32-vulkan-radeon``
   * - Intel
     - ``mesa``, ``lib32-mesa``, ``vulkan-intel``, ``intel-media-driver``
   * - Hybrid / dual GPU
     - union of the driver sets plus ``envycontrol`` (GPU switching)
   * - Virtual machine (VMware/QXL/virtio/...)
     - ``mesa``
   * - Unclassified / detection failure
     - ``mesa`` (open-source fallback)

NVIDIA generation classification
--------------------------------

Turing and newer cards are recognized from their marketing names
(``RTX``/``GTX 16``/``Quadro RTX``/``RTX Pro``/Ada/Blackwell markers) and get
the open kernel module; pre-Turing devices without such markers fall back to
``nouveau`` because the proprietary legacy driver is no longer packaged.

The resolved plan is mapped onto archinstall's regular
``ProfileConfiguration.gfx_driver`` when possible, so the driver selection is
also visible and editable in the guided profile menu.  After a proprietary
NVIDIA or hybrid installation the initramfs is regenerated
(``mkinitcpio -P``) so the driver modules are picked up on first boot.
