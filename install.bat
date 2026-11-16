@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ======================================================================
echo   🎬 INSTALADOR 1-CLIC: AFTER EFFECTS PRO MCP SERVER (FastMCP)
echo ======================================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python instalado en el PATH.
    echo Descarga e instala Python 3.10+ desde https://www.python.org/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creando entorno virtual Python (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Fallo la creacion del entorno virtual.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Entorno virtual (.venv) ya existe.
)

echo.
echo [2/3] Instalando dependencias (FastMCP y psutil)...
".venv\Scripts\pip.exe" install -r requirements.txt

echo.
echo [3/3] Autodetectando After Effects, instalando Panel y registrando MCP...
".venv\Scripts\python.exe" setup_installer.py

echo.
pause
