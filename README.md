<div align="center">
<img src="docs/logo.png" alt="archinstall logo" width="200"/>
</div>

# archinstall but better

An opinionated fork of archinstall featuring an automated Preset vs. Custom workflow, native CachyOS repositories, dynamic GPU detection, and drop-privileged dotfile deployment.


## Quick Start

Run directly from source on an official Arch Linux ISO:

```
git clone https://github.com/callenflynn/archinstall.git
cd archinstall
python -m archinstall
```

## Preset vs. Custom Defaults

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

## Developer Guide

### Local Testing & Linting

```shell
# Unit tests
pytest tests/

# Type checking & linting
mypy
ruff check archinstall/ tests/

# Build wheel package
python -m build
```