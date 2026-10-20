# EFI Boot Order Manager

A small Linux GUI for viewing and changing the UEFI `BootOrder` with `efibootmgr`.

## Requirements

- A Linux system booted in UEFI mode
- Python 3.10 or newer
- `efibootmgr`
- `pkexec` (provided by polkit) to authorize changes from the GUI

On Arch Linux and derivatives, install the system tools with:

```bash
sudo pacman -S efibootmgr polkit
```

On Debian or Ubuntu, use:

```bash
sudo apt install efibootmgr policykit-1
```

## Download and run

Download or clone this project, then open a terminal in the `efi` directory (the directory containing `app.py`). Create and activate a virtual environment, install the Python dependency, and start the app:

```bash
git clone https://github.com/C2dan88/efiboot.git
cd efiboot
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## Using the app

Entries are shown in their current boot order. Select an entry and use **Move up** or **Move down** to change its position. Checked entries are included in the new `BootOrder`; unchecking an entry leaves its `Boot####` entry on the system but removes it from `BootOrder`. Click **Apply order** and confirm to write the change. The system will request administrator authorization through `pkexec`.

Entries marked **[disabled]** are not enabled by changing `BootOrder`; this app does not change their enabled/disabled state. Use **Reload** to discard unsaved list changes and reread the firmware settings.

Changing UEFI boot settings can affect startup. Review the proposed order carefully before applying it.
