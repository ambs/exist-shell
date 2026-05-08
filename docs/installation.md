# Installation

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) — used both to install `exsh` and to manage dev dependencies

## Install as a tool

The recommended way is to install `exsh` as a uv tool so it is available system-wide:

```bash
uv tool install git+https://github.com/ambs/exist-shell
```

Verify the installation:

```bash
exsh --version
```

## Upgrade

```bash
uv tool upgrade exist-shell
```

## Uninstall

```bash
uv tool uninstall exist-shell
```

## Install from a local clone

If you want to develop or test from source:

```bash
git clone https://github.com/ambs/exist-shell
cd exist-shell
uv sync
```

The `exsh` command is then available inside the project's virtual environment:

```bash
.venv/bin/exsh --help
```

Or activate the environment first:

```bash
source .venv/bin/activate
exsh --help
```
