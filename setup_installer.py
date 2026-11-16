"""
Universal Setup & Auto-Configurator for After Effects Pro MCP
=============================================================
Run automatically by `install.bat` (or via `python setup_installer.py`).
- Detects all installed Adobe After Effects versions on the machine
- Enables Scripting & Network permissions (`Pref_SCRIPTING_FILE_NETWORK_SECURITY = 1`)
- Installs `AE_MCP_Pro_Panel.jsx` and `AE_MCP_AutoPermissions.jsx`
- Registers the MCP server in Antigravity, Cursor, and Claude Desktop configs
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable).resolve()

SERVER_PY = BASE_DIR / "server.py"


def register_in_mcp_json(config_path: Path, create_if_missing: bool = False) -> bool:
    """Adds or updates `after-effects-pro` inside an MCP JSON configuration file."""
    if not config_path.exists():
        if not create_if_missing:
            return False
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"mcpServers": {}}
    else:
        try:
            raw = config_path.read_text(encoding="utf-8").strip()
            data = json.loads(raw) if raw else {"mcpServers": {}}
        except Exception:
            data = {"mcpServers": {}}

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    data["mcpServers"]["after-effects-pro"] = {
        "command": str(VENV_PYTHON),
        "args": [str(SERVER_PY)],
    }

    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def main() -> None:
    print("=" * 70)
    print("  AFTER EFFECTS PRO MCP - CONFIGURADOR AUTOMATICO UNIVERSAL")
    print("=" * 70)

    # Import helpers from server.py
    sys.path.insert(0, str(BASE_DIR))
    from server import discover_installed_ae_executables, ensure_ae_disk_permissions

    exes = discover_installed_ae_executables()
    if exes:
        print(f"\n[OK] Versiones de After Effects detectadas ({len(exes)}):")
        for exe in exes:
            print(f"     - {exe}")
    else:
        print(
            "\n[!] No se detecto AfterFX.exe en la ruta estandar (C:\\Program Files\\Adobe)."
            "\n    Si lo tenes en otra ruta, podes definir AE_EXECUTABLE_PATH."
        )

    perms_info = ensure_ae_disk_permissions()
    print(f"\n[OK] Permisos y Panel instalados para versiones: {', '.join(perms_info['configured_versions'])}")
    for p in perms_info["installed_panels"]:
        print(f"     - Panel: {p}")

    # Register in Antigravity (~/.gemini/config/mcp_config.json)
    home = Path.home()
    agy_config = home / ".gemini" / "config" / "mcp_config.json"
    if register_in_mcp_json(agy_config, create_if_missing=True):
        print(f"\n[OK] Registrado en Antigravity: {agy_config}")

    # Optional: Register in Cursor (~/.cursor/mcp.json) if ~/.cursor exists
    cursor_dir = home / ".cursor"
    if cursor_dir.exists():
        cursor_cfg = cursor_dir / "mcp.json"
        if register_in_mcp_json(cursor_cfg, create_if_missing=True):
            print(f"[OK] Registrado en Cursor:      {cursor_cfg}")

    # Optional: Register in Claude Desktop if %APPDATA%\Claude exists
    appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    claude_dir = appdata / "Claude"
    if claude_dir.exists():
        claude_cfg = claude_dir / "claude_desktop_config.json"
        if register_in_mcp_json(claude_cfg, create_if_missing=True):
            print(f"[OK] Registrado en Claude:      {claude_cfg}")

    print("\n" + "=" * 70)
    print("  INSTALACION COMPLETADA CON EXITO!")
    print("  Reinicia o recarga los MCP Servers en tu editor y abri After Effects.")
    print("=" * 70)


if __name__ == "__main__":
    main()
