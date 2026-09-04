<div align="center">
<img src="docs/logo.png" alt="archinstall logo" width="200"/>
</div>

# archinstall — Cal's Preset fork

A fork of [Arch Linux's archinstall](https://github.com/archlinux/archinstall)
(an easy, guided/automated Arch Linux installer that also doubles as a Python
library) with a streamlined **Preset vs. Custom** installation workflow,
**CachyOS repository** integration, **dynamic GPU driver detection** and
**secured dotfile deployment**.

## Key features

* **Entry-screen choice.** The moment the guided installer launches you pick:
  - **Cal's Preset** *(Recommended - Fast setup with Hyprland + Ambxst)* — a
    fully automated installation. Ask for a locale, credentials and a target
    disk, then everything is applied automatically.
  - **Custom Setup** *(Granular step-by-step configuration)* — the classic
    flow with opinionated defaults pre-selected.
* **Cal's Preset defaults** — Hyprland, `Ambxst` dotfiles,
  `greetd + tuigreet`, ext4 + zram swap, `systemd-boot`, `pipewire`, `paru`,
  full-sudo `wheel` user (root password mirrors the user password).
* **CachyOS repositories as primary package providers** with automatic CPU
  ISA-level detection (`v3` / `v4` / `znver4`, generic `[cachyos]` fallback),
  key import/signing (`F3B607488DB35A47`), keyring+mirrorlist packages
  strapped with the base system, and a synchronized `pacman -Syu` — never a
  partial `-Sy`.
* **Dynamic hardware probing** — live GPU detection selects the right driver
  set (NVIDIA Turing+ open kernel module, AMD, Intel, hybrid with
  `envycontrol`, VM/open-source fallbacks) and auto-detected
  display manager recommendations per desktop.
* **Secured dotfile deployment** — third-party repos are cloned as the target
  user, inspected before running, executed strictly drop-privileged
  (never `curl | sh`, never root), and home ownership is repaired on success
  *and* failure.
* **Explicit failure policy** — critical steps (GPG key import, base
  packages, user creation, partitioning) abort with clear errors; optional
  steps (mirror ranking, GPU detection, dotfiles) warn, fall back safely and
  continue.

## Quick start

> The fork's guided flow is built for the **official Arch Linux ISO**
> (root by default). Run from source to get this fork's code:

```shell
git clone <this-repository>
cd archinstall
python -m archinstall
```

You will be greeted by the entry screen:

1. **Cal's Preset** — answer the four prompts (locale → username/password →
   target disk); mirrors are auto-ranked, then the preset installs itself.
2. **Custom Setup** — choose desktop environment (KDE Plasma / Hyprland
   recommended, GNOME, Cinnamon, XFCE or Minimal CLI), the Hyprland dotfiles
   suite, and confirm the recommended display manager.

Installation from the Arch package manager is also supported (this installs
whatever `archinstall` version the repositories carry):

```shell
pacman-key --init
pacman -Sy archinstall
archinstall
```

### Cal's Preset defaults at a glance

| Component            | Default                                                        |
| -------------------- | -------------------------------------------------------------- |
| Desktop environment  | Hyprland                                                       |
| Dotfiles suite       | Ambxst (https://github.com/Axenide/Ambxst)                     |
| Display manager      | greetd + tuigreet (`greetd.service`)                           |
| Filesystem / swap    | ext4 best-effort layout, zram swap                             |
| Bootloader           | systemd-boot                                                   |
| Audio stack          | pipewire                                                       |
| AUR helper           | paru (guarded, only when the repositories provide it)          |
| Repositories         | CachyOS with automatic ISA-level detection                     |
| GPU drivers          | automatic detection + driver selection                         |
| User                 | `wheel` with full sudo; root password = user password          |

### Display manager recommendations (Custom Setup)

| Desktop        | Recommended display manager |
| -------------- | --------------------------- |
| Hyprland       | greetd + tuigreet           |
| KDE Plasma     | SDDM                        |
| GNOME          | GDM                         |
| Cinnamon / XFCE| LightDM                     |
| Minimal CLI    | none (prompt bypassed)      |

## CLI usage

All upstream CLI options are supported:

```shell
# run an alternative script (see archinstall/scripts)
archinstall --script <name>

# hidden/advanced options
archinstall --advanced

# declarative configuration files (general + sensitive credentials)
archinstall --config <path-or-url> --creds <path-or-url>

# preview a run and dump the resulting configuration without touching the disk
archinstall --dry-run

# encrypt the saved credentials file
archinstall --config config.json --creds creds.json --creds-decryption-key <password>
```

A complete description of every option is available via `archinstall -h` /
`archinstall --help` and in the [config reference](docs/installing/guided.rst).

## Documentation

* [Fork guide — Preset vs. Custom](docs/fork/index.rst)
  * [Cal's Preset defaults](docs/fork/cal_preset.rst)
  * [CachyOS repository integration](docs/fork/cachyos.rst)
  * [GPU detection & driver selection](docs/fork/hardware.rst)
  * [Display manager selection & greetd + tuigreet](docs/fork/display_manager.rst)
  * [Secured dotfile deployment](docs/fork/dotfiles.rst)
* [Guided installation guide](docs/installing/guided.rst)
* [Known issues](docs/help/known_issues.rst)
* [Example configuration](examples/config-sample.json) and
  [example credentials](examples/creds-sample.json)

The Sphinx documentation in [`docs/`](docs/) is published to GitHub Pages by
[`.github/workflows/deploy-docs.yml`](.github/workflows/deploy-docs.yml) on
every push to `main`/`master`.

## Testing

Unit tests (no root, no hardware — the fork logic is pure):

```shell
pytest tests/
```

Lint and types (as enforced by CI):

```shell
ruff check archinstall/ tests/
ruff format --check archinstall/ tests/
mypy                     # uses pyproject.toml; include stubs/ for parted
```

Build the Python distribution:

```shell
python -m build
```

To test against a real live medium, boot the latest
[Arch Linux ISO](https://archlinux.org/download/) in a VM, clone this
repository, and run `python -m archinstall` inside it. See the upstream
[Building and Testing](https://github.com/archlinux/archinstall/wiki/Building-and-Testing)
guide for the full QEMU workflow.

## FAQ

**Does the fork still support vanilla Arch?** Yes. The CachyOS repository
opt-in is per-run (default on in both fork modes; the Custom Setup flow asks
first). Declarative `--config` runs without the fork fields behave exactly
like upstream archinstall.

**AUR helpers?** Upstream archinstall deliberately does not offer AUR
helpers. This fork can install `paru` from the configured repositories
(guarded — failure to install it only logs a warning and continues).

**Keyring out of date?** See the upstream
[keyring troubleshooting](https://archinstall.archlinux.page/help/known_issues.html#keyring-is-out-of-date-2213);
`pacman -Sy archlinux-keyring` is the quick fix on an outdated ISO.

## Upstream & license

This fork is based on upstream archinstall and follows its principles: a
guided installer that ships safe defaults while remaining fully
configurable, running entirely on the official Arch Linux ISO. Upstream
community channels:

* [Discord](https://discord.gg/aDeMffrxNg)
* [#archinstall:matrix.org](https://matrix.to/#/#archinstall:matrix.org)
* [Upstream documentation](https://archinstall.archlinux.page/)

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and the
[license](LICENSE) for terms.
