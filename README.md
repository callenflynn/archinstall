<div align="center">
<img src="docs/logo.png" alt="archinstall logo" width="200"/>
</div>

# archinstall but better

An opinionated fork of archinstall featuring an automated Preset vs. Custom workflow, native CachyOS repositories, dynamic GPU detection, and drop-privileged dotfile deployment.


## Quick Start

### Option 1: The fork ISO (Recommended)

Grab `archinstall-fork-<version>.iso` from the
[latest release](https://github.com/callenflynn/archinstall/releases/latest),

### Option 2: From a stock Arch ISO (no git required)


```
curl -LO https://github.com/callenflynn/archinstall/releases/latest/download/archinstall-fork.pyz
sudo python archinstall-fork.pyz
```

### Option 3: From source

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