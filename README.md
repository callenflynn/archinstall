<div align="center">
<img src="docs/logo.png" alt="archinstall logo" width="200"/>
</div>

# archinstall (Cal's Preset Fork)

An opinionated fork of archinstall featuring an automated Preset vs. Custom workflow, native CachyOS repositories, dynamic GPU detection, and drop-privileged dotfile deployment.
Features
 * Dual-Mode Setup:
   * Cal's Preset (Automated): 4-prompt setup (locale, user/pass, target disk) installing Hyprland + Ambxst.
   * Custom Setup (Granular): Classic guided installer with opinionated defaults pre-selected.
 * CachyOS Repositories: Auto-detects CPU ISA (v3, v4, znver4, or generic [cachyos]) with pre-configured keyrings and synchronized pacman -Syu.
 * Hardware & DM Matching: Probes GPUs (NVIDIA Turing+ open module, AMD, Intel, Hybrid/EnvyControl) and automatically pairs DEs with recommended DMs (e.g., Hyprland \rightarrow greetd + tuigreet).
 * Secure Dotfiles: Clones and runs third-party setups strictly drop-privileged (su - <user>), repairing permissions on completion or failure.
Quick Start
Run directly from source on an official Arch Linux ISO:
git clone <repository-url>
cd archinstall
python -m archinstall

Preset vs. Custom Defaults
| Feature | Cal's Preset | Custom Setup Recommendation |
|---|---|---|
| Desktop | Hyprland | Choice (Hyprland, Plasma, GNOME, etc.) |
| Display Manager | greetd + tuigreet | Matched per DE (SDDM, GDM, LightDM) |
| Dotfiles | Ambxst | Choice / Optional |
| Filesystem / Swap | Best-effort ext4 + zram | Configurable |
| Bootloader | systemd-boot | Configurable |
| Audio | pipewire | pipewire |
| Repos & Hardware | CachyOS + Auto GPU drivers | CachyOS (opt-out) + Auto GPU drivers |
| Privileges | wheel (sudo) + mirrored root pass | Configurable |
Developer Guide
Local Testing & Linting
# Unit tests
pytest tests/

# Type checking & linting
mypy
ruff check archinstall/ tests/

# Build wheel package
python -m build

