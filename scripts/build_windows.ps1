$ErrorActionPreference = "Stop"

python -m pip install -e ".[dev]"
python -m PyInstaller --clean --noconfirm packaging\sonora.spec
