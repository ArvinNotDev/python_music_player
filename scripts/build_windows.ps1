$ErrorActionPreference = "Stop"

python -m pip install -e ".[dev]"
python scripts\generate_app_icon.py
python -m PyInstaller --clean --noconfirm packaging\rw_player.spec
