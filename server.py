"""
After Effects v27.0 PRO MCP Server (Powered by FastMCP)
=======================================================
Provides full, fault-tolerant, undo-safe control over Adobe After Effects 2027 (v27.0).

Features:
- Zero-crash execution engine with atomic UTF-8 JSON IPC
- Automatic Undo Group wrapping (Ctrl+Z undoes any AI action)
- Automatic Composition Snapshot Backups (_MCP_SNAPSHOTS)
- Automatic Scripting & Network permission configuration for AE 27.0
- No flashing console windows on Windows (CREATE_NO_WINDOW)
- 14 specialized tools for inspection, timeline editing, effects, keyframes,
  expressions, frame preview rendering, and custom ExtendScript execution.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil
from fastmcp import FastMCP

# ==============================================================================
# PATHS & CONFIGURATION
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
BRIDGE_DIR = BASE_DIR / "bridge"
REQ_DIR = BRIDGE_DIR / "requests"
RES_DIR = BRIDGE_DIR / "responses"
PREVIEW_DIR = BRIDGE_DIR / "previews"
JSX_DIR = BASE_DIR / "jsx"
RUNTIME_JSX_PATH = JSX_DIR / "ae_mcp_runtime.jsx"
HISTORY_LOG_PATH = BRIDGE_DIR / "history.jsonl"

for d in (REQ_DIR, RES_DIR, PREVIEW_DIR, JSX_DIR):
    d.mkdir(parents=True, exist_ok=True)

APPDATA_ROAMING = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
AE_APPDATA_ROOT = APPDATA_ROAMING / "Adobe" / "After Effects"

mcp = FastMCP(
    "after-effects-pro",
    instructions=(
        "Servidor MCP Profesional para controlar Adobe After Effects (2024/2025/2026/2027+). "
        "Permite inspeccionar proyectos, composiciones, capas, efectos y propiedades, "
        "modificar el timeline con seguridad (Undo Groups y Snapshots automáticos), "
        "aplicar efectos, keyframes, expresiones, renderizar vistas previas PNG para "
        "inspección visual y ejecutar código ExtendScript (.jsx) directo."
    ),
)


# ==============================================================================
# HELPER FUNCTIONS (PROCESS, PERMISSIONS & IPC BRIDGE)
# ==============================================================================

def discover_installed_ae_executables() -> List[Path]:
    """Dynamically discovers all installed AfterFX.exe paths sorted newest first."""
    candidates: List[Path] = []

    env_exe = os.environ.get("AE_EXECUTABLE_PATH")
    if env_exe and Path(env_exe).exists():
        candidates.append(Path(env_exe))

    prog_files_dirs = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Adobe",
        Path(r"C:\Program Files\Adobe"),
        Path(r"D:\Program Files\Adobe"),
        Path(r"E:\Program Files\Adobe"),
    ]
    seen = set()
    found_dirs: List[Path] = []
    for adobe_root in prog_files_dirs:
        if adobe_root.exists():
            for d in adobe_root.glob("Adobe After Effects*"):
                exe = d / "Support Files" / "AfterFX.exe"
                if exe.exists() and str(exe) not in seen:
                    seen.add(str(exe))
                    found_dirs.append(exe)

    # Sort descending so 2027 > 2026 > 2025 > 2024
    found_dirs.sort(key=lambda p: p.parent.parent.name, reverse=True)
    candidates.extend(found_dirs)
    return candidates


def get_ae_executable() -> Path:
    """Finds the best AfterFX.exe binary (prioritizing running instance, then newest installed)."""
    running = get_running_ae_process()
    if running and running.get("exe"):
        exe_path = Path(running["exe"])
        if exe_path.exists():
            return exe_path

    candidates = discover_installed_ae_executables()
    if candidates:
        return candidates[0]

    raise FileNotFoundError(
        "No se encontró AfterFX.exe instalado. "
        "Verifica la instalación de Adobe After Effects o definí la variable AE_EXECUTABLE_PATH."
    )


def get_running_ae_process() -> Optional[Dict[str, Any]]:
    """Checks if AfterFX.exe is currently running and returns process details."""
    for proc in psutil.process_iter(["pid", "name", "exe", "memory_info", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in ("afterfx.exe", "afterfx.com"):
                mem_mb = 0.0
                if proc.info.get("memory_info"):
                    mem_mb = round(proc.info["memory_info"].rss / (1024 * 1024), 1)
                return {
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "exe": proc.info.get("exe"),
                    "memory_mb": mem_mb,
                    "uptime_seconds": round(time.time() - (proc.info.get("create_time") or time.time()), 1),
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def ensure_ae_disk_permissions(version: Optional[str] = None) -> Dict[str, Any]:
    """
    Ensures 'Allow Scripts to Write Files and Access Network'
    (Pref_SCRIPTING_FILE_NETWORK_SECURITY = 1) is enabled in AE prefs on disk,
    and installs the ScriptUI Panel & Startup script across installed AE versions.
    """
    AE_APPDATA_ROOT.mkdir(parents=True, exist_ok=True)
    target_dirs: List[Path] = []

    if version:
        v_dir = AE_APPDATA_ROOT / version
        v_dir.mkdir(parents=True, exist_ok=True)
        target_dirs.append(v_dir)

    for sub in AE_APPDATA_ROOT.iterdir():
        if sub.is_dir() and re.match(r"^\d+\.\d+", sub.name) and sub not in target_dirs:
            target_dirs.append(sub)

    if not target_dirs:
        default_v = AE_APPDATA_ROOT / "27.0"
        default_v.mkdir(parents=True, exist_ok=True)
        target_dirs.append(default_v)

    prefs_updated = []
    installed_panels = []
    installed_startups = []

    src_panel = JSX_DIR / "AE_MCP_Pro_Panel.jsx"
    src_startup = JSX_DIR / "AE_MCP_AutoPermissions.jsx"

    for ver_dir in target_dirs:
        for pref_file in ver_dir.glob("*Pref*.txt"):
            try:
                content = pref_file.read_text(encoding="utf-8", errors="ignore")
                if '"Pref_SCRIPTING_FILE_NETWORK_SECURITY"' in content:
                    new_content = re.sub(
                        r'("Pref_SCRIPTING_FILE_NETWORK_SECURITY"\s*=\s*)"0"',
                        r'\1"1"',
                        content,
                    )
                    if new_content != content:
                        pref_file.write_text(new_content, encoding="utf-8")
                        prefs_updated.append(str(pref_file))
            except Exception:
                pass

        scripts_dir = ver_dir / "Scripts"
        panel_dir = scripts_dir / "ScriptUI Panels"
        startup_dir = scripts_dir / "Startup"
        panel_dir.mkdir(parents=True, exist_ok=True)
        startup_dir.mkdir(parents=True, exist_ok=True)

        if src_panel.exists():
            dst_panel = panel_dir / "AE_MCP_Pro_Panel.jsx"
            shutil.copy2(src_panel, dst_panel)
            installed_panels.append(str(dst_panel))

        if src_startup.exists():
            dst_startup = startup_dir / "AE_MCP_AutoPermissions.jsx"
            shutil.copy2(src_startup, dst_startup)
            installed_startups.append(str(dst_startup))

    return {
        "configured_versions": [d.name for d in target_dirs],
        "prefs_updated_on_disk": prefs_updated,
        "installed_panels": installed_panels,
        "installed_startups": installed_startups,
    }


def log_execution(entry: Dict[str, Any]) -> None:
    """Appends an execution record to bridge/history.jsonl."""
    try:
        entry["timestamp"] = datetime.datetime.now().isoformat()
        with open(HISTORY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


_AE_EXEC_LOCK = asyncio.Lock()


async def execute_in_ae(
    jsx_body: str,
    undo_name: Optional[str] = "MCP Action",
    suppress_dialogs: bool = True,
    auto_backup_comp: Optional[str] = None,
    timeout_seconds: float = 30.0,
    auto_launch: bool = False,
) -> Dict[str, Any]:
    """
    Core fault-tolerant IPC executor (serialized via _AE_EXEC_LOCK).
    1. Wraps `jsx_body` with `ae_mcp_runtime.jsx`, Undo Group, Dialog Suppression,
       and atomic UTF-8 JSON file writing.
    2. Dispatches `AfterFX.exe -r <req.jsx>` without popping up a console window.
    3. Polls for `<res.json>` and returns the parsed result.
    """
    async with _AE_EXEC_LOCK:
        proc_info = get_running_ae_process()
        if not proc_info:
            if auto_launch:
                exe = get_ae_executable()
                ensure_ae_disk_permissions()
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                subprocess.Popen([str(exe)], creationflags=creationflags)
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    proc_info = get_running_ae_process()
                    if proc_info:
                        break
                await asyncio.sleep(5.0)
            else:
                return {
                    "ok": False,
                    "error": (
                        "After Effects no está abierto en este momento. "
                        "Podés abrirlo o llamar a la herramienta `ae_launch_and_setup`."
                    ),
                    "ae_running": False,
                }

        req_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        req_file = REQ_DIR / f"req_{req_id}.jsx"
        res_file = RES_DIR / f"res_{req_id}.json"
        res_tmp_file = RES_DIR / f"res_{req_id}.tmp"

        runtime_code = RUNTIME_JSX_PATH.read_text(encoding="utf-8")
        res_path_js = str(res_file).replace("\\", "/")
        res_tmp_path_js = str(res_tmp_file).replace("\\", "/")

        undo_js = json.dumps(undo_name) if undo_name else "null"
        suppress_js = "true" if suppress_dialogs else "false"
        backup_comp_js = json.dumps(auto_backup_comp) if auto_backup_comp else "null"

        full_jsx = f"""// AE MCP PRO REQUEST: {req_id}
{runtime_code}

(function () {{
    var __resTmpPath = {json.dumps(res_tmp_path_js)};
    var __resFinalPath = {json.dumps(res_path_js)};
    var __undoName = {undo_js};
    var __suppress = {suppress_js};
    var __backupCompTarget = {backup_comp_js};
    var __undoStarted = false;
    var __suppressStarted = false;
    var __backupInfo = null;
    var __envelope = {{
        ok: false,
        req_id: {json.dumps(req_id)},
        ae_version: app.version,
        project_file: (app.project && app.project.file) ? app.project.file.fsName : null,
        result: null,
        backup: null,
        error: null
    }};

    try {{
        AEMCP.ensurePermissions();

        if (__suppress) {{
            try {{
                app.beginSuppressDialogs();
                __suppressStarted = true;
            }} catch (eSup) {{}}
        }}

        if (__undoName) {{
            app.beginUndoGroup(__undoName);
            __undoStarted = true;
        }}

        if (__backupCompTarget !== null) {{
            var __cToBackup = AEMCP.findComp(__backupCompTarget === "__ACTIVE__" ? null : __backupCompTarget);
            if (__cToBackup) {{
                __backupInfo = AEMCP.backupComp(__cToBackup);
                __envelope.backup = __backupInfo;
            }}
        }}

        var __userFn = function () {{
{jsx_body}
        }};

        __envelope.result = __userFn();
        __envelope.ok = true;
    }} catch (err) {{
        __envelope.ok = false;
        __envelope.error = {{
            message: String(err.message || err),
            name: String(err.name || "ExtendScriptError"),
            line: err.line || null,
            fileName: err.fileName || null
        }};
    }} finally {{
        if (__undoStarted) {{
            try {{ app.endUndoGroup(); }} catch (eUndo) {{}}
        }}
        if (__suppressStarted) {{
            try {{ app.endSuppressDialogs(false); }} catch (eEndSup) {{}}
        }}
        try {{
            var __jsonStr = JSON.stringify(__envelope);
            var __fTmp = new File(__resTmpPath);
            __fTmp.encoding = "UTF-8";
            if (__fTmp.open("w")) {{
                __fTmp.write(__jsonStr);
                __fTmp.close();
                var __fFinal = new File(__resFinalPath);
                if (__fFinal.exists) __fFinal.remove();
                __fTmp.rename(__fFinal.name);
            }}
        }} catch (eWrite) {{}}
    }}
}})();
"""

        # Write with UTF-8 BOM (utf-8-sig) so ExtendScript always parses UTF-8 on any Windows locale
        req_file.write_text(full_jsx, encoding="utf-8-sig")
        exe_path = get_ae_executable()

        t0 = time.perf_counter()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        subprocess.Popen(
            [str(exe_path), "-r", str(req_file)],
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.perf_counter() + timeout_seconds
        response_data: Optional[Dict[str, Any]] = None

        while time.perf_counter() < deadline:
            if res_file.exists():
                try:
                    raw_text = res_file.read_text(encoding="utf-8")
                    if raw_text.strip():
                        response_data = json.loads(raw_text)
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.06)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        for temp_f in (req_file, res_file, res_tmp_file):
            try:
                if temp_f.exists():
                    temp_f.unlink()
            except Exception:
                pass

        if response_data is None:
            err_out = {
                "ok": False,
                "req_id": req_id,
                "elapsed_ms": elapsed_ms,
                "error": (
                    f"Timeout ({timeout_seconds}s) esperando respuesta de After Effects. "
                    "Posibles causas: 1) After Effects todavía está cargando la pantalla de inicio, "
                    "2) Hay una ventana modal/cartel abierto en After Effects esperando clic, "
                    "o 3) En Editar > Preferencias > Scripts y expresiones falta activar "
                    "'Permitir que los scripts puedan escribir archivos y acceder a la red'."
                ),
            }
            log_execution({"req_id": req_id, "undo_name": undo_name, "ok": False, "elapsed_ms": elapsed_ms, "timeout": True})
            return err_out

        response_data["elapsed_ms"] = elapsed_ms
        log_execution({
            "req_id": req_id,
            "undo_name": undo_name,
            "ok": response_data.get("ok", False),
            "elapsed_ms": elapsed_ms,
            "error": response_data.get("error"),
        })
        return response_data


# ==============================================================================
# MCP TOOLS
# ==============================================================================

@mcp.tool()
async def ae_status() -> Dict[str, Any]:
    """
    Verifica el estado completo de After Effects v27.0: si el proceso está corriendo,
    uso de memoria RAM, ruta del ejecutable, permisos en disco y estado del proyecto activo.
    """
    proc = get_running_ae_process()
    exe_str = None
    try:
        exe_str = str(get_ae_executable())
    except Exception as e:
        exe_str = f"Not found: {e}"

    perms = ensure_ae_disk_permissions()
    status_info: Dict[str, Any] = {
        "ae_running": proc is not None,
        "process": proc,
        "ae_executable": exe_str,
        "permissions_setup": perms,
    }

    if proc is not None:
        ping = await execute_in_ae(
            """
            return {
                version: app.version,
                buildName: app.buildName,
                isoLanguage: app.isoLanguage,
                memoryInUseKB: app.memoryInUse,
                projectPath: (app.project && app.project.file) ? app.project.file.fsName : null,
                numItems: app.project ? app.project.numItems : 0,
                activeComp: (app.project && app.project.activeItem instanceof CompItem) ? {
                    id: app.project.activeItem.id,
                    name: app.project.activeItem.name,
                    width: app.project.activeItem.width,
                    height: app.project.activeItem.height,
                    frameRate: app.project.activeItem.frameRate,
                    duration: app.project.activeItem.duration,
                    numLayers: app.project.activeItem.numLayers
                } : null
            };
            """,
            undo_name=None,
            timeout_seconds=10.0,
        )
        status_info["live_bridge"] = ping

    return status_info


@mcp.tool()
async def ae_launch_and_setup(
    project_path: Optional[str] = None,
    wait_until_ready: bool = True,
) -> Dict[str, Any]:
    """
    Prepara los permisos de After Effects, instala el panel Pro en ScriptUI Panels,
    inicia After Effects si está cerrado y opcionalmente abre un archivo de proyecto (.aep)
    suprimiendo carteles modales de advertencia ('plugin no instalado' / 'convertir versión').
    """
    perms = ensure_ae_disk_permissions()
    proc = get_running_ae_process()
    exe = get_ae_executable()

    if not proc:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        # IMPORTANTE: No pasar project_path por línea de comandos para evitar carteles modales
        # ('Plugin no instalado' o 'Proyecto convertido') antes de que corra app.beginSuppressDialogs().
        subprocess.Popen([str(exe)], creationflags=creationflags)

        if wait_until_ready:
            for _ in range(60):
                await asyncio.sleep(0.5)
                proc = get_running_ae_process()
                if proc:
                    break
            # Esperar a que el motor ExtendScript responda al primer ping
            for _ in range(12):
                ping = await execute_in_ae("return app.version;", undo_name=None, timeout_seconds=5.0)
                if ping.get("ok"):
                    break
                await asyncio.sleep(1.5)

    if project_path and Path(project_path).exists():
        abs_aep = str(Path(project_path).resolve()).replace("\\", "/")
        open_res = await execute_in_ae(
            f"""
            var f = new File({json.dumps(abs_aep)});
            if (!f.exists) throw new Error("No existe el archivo: " + f.fsName);
            if (!app.project || !app.project.file || app.project.file.fsName !== f.fsName) {{
                app.open(f);
            }}
            return {{
                opened: app.project.file ? app.project.file.fsName : null,
                numItems: app.project.numItems
            }};
            """,
            undo_name=None,
            suppress_dialogs=True,
            timeout_seconds=40.0,
        )
        return {"setup": perms, "process": proc, "project": open_res}

    return {"setup": perms, "process": proc}


@mcp.tool()
async def ae_get_project_overview(include_footage_paths: bool = True) -> Dict[str, Any]:
    """
    Obtiene el mapa completo del proyecto abierto en After Effects:
    todas las composiciones, carpetas y archivos importados (videos, audios, imágenes).
    """
    inc_js = "true" if include_footage_paths else "false"
    return await execute_in_ae(
        f"""
        if (!app.project) throw new Error("No hay proyecto activo.");
        var comps = [];
        var folders = [];
        var footage = [];
        var activeId = (app.project.activeItem) ? app.project.activeItem.id : null;

        for (var i = 1; i <= app.project.numItems; i++) {{
            var it = app.project.item(i);
            if (it instanceof CompItem) {{
                comps.push({{
                    id: it.id,
                    name: it.name,
                    isActive: (it.id === activeId),
                    width: it.width,
                    height: it.height,
                    frameRate: Math.round(it.frameRate * 1000) / 1000,
                    duration: Math.round(it.duration * 1000) / 1000,
                    workAreaStart: Math.round(it.workAreaStart * 1000) / 1000,
                    workAreaDuration: Math.round(it.workAreaDuration * 1000) / 1000,
                    time: Math.round(it.time * 1000) / 1000,
                    numLayers: it.numLayers,
                    parentFolder: it.parentFolder ? it.parentFolder.name : "Root"
                }});
            }} else if (it instanceof FolderItem) {{
                folders.push({{
                    id: it.id,
                    name: it.name,
                    numItems: it.numItems,
                    parentFolder: it.parentFolder ? it.parentFolder.name : "Root"
                }});
            }} else if (it instanceof FootageItem) {{
                var ft = {{
                    id: it.id,
                    name: it.name,
                    width: it.width,
                    height: it.height,
                    duration: Math.round((it.duration || 0) * 1000) / 1000,
                    frameRate: Math.round((it.frameRate || 0) * 1000) / 1000,
                    hasVideo: it.hasVideo,
                    hasAudio: it.hasAudio,
                    footageMissing: it.footageMissing
                }};
                if ({inc_js} && it.file) {{
                    ft.filePath = it.file.fsName;
                }}
                footage.push(ft);
            }}
        }}
        return {{
            projectFile: app.project.file ? app.project.file.fsName : "Untitled Project",
            numItems: app.project.numItems,
            bitsPerChannel: app.project.bitsPerChannel,
            compositions: comps,
            folders: folders,
            footageCount: footage.length,
            footage: footage.slice(0, 150)
        }};
        """,
        undo_name=None,
    )


@mcp.tool()
async def ae_inspect_composition(
    comp_name_or_id: Optional[str] = None,
    include_transform: bool = True,
    include_effects: bool = True,
    include_effect_params: bool = False,
    start_layer: int = 1,
    max_layers: int = 100,
) -> Dict[str, Any]:
    """
    Inspecciona en detalle una composición (o la composición activa si se omite `comp_name_or_id`).
    Devuelve resolución, FPS, playhead, marcadores y todas sus capas con tiempos, modos de fusión,
    transformaciones, efectos y textos.
    """
    target_js = json.dumps(comp_name_or_id) if comp_name_or_id else "null"
    tr_js = "true" if include_transform else "false"
    fx_js = "true" if include_effects else "false"
    fxp_js = "true" if include_effect_params else "false"

    return await execute_in_ae(
        f"""
        var comp = AEMCP.findComp({target_js});
        if (!comp) throw new Error("No se encontró la composición solicitada.");

        var layers = [];
        var startIdx = Math.max(1, {int(start_layer)});
        var endIdx = Math.min(comp.numLayers, startIdx + {int(max_layers)} - 1);

        for (var i = startIdx; i <= endIdx; i++) {{
            var lyr = comp.layer(i);
            layers.push(AEMCP.serializeLayer(lyr, {{
                includeTransform: {tr_js},
                includeEffects: {fx_js},
                includeEffectParams: {fxp_js}
            }}));
        }}

        var markers = [];
        try {{
            if (comp.markerProperty && comp.markerProperty.numKeys > 0) {{
                for (var m = 1; m <= comp.markerProperty.numKeys; m++) {{
                    var mv = comp.markerProperty.keyValue(m);
                    markers.push({{
                        index: m,
                        time: Math.round(comp.markerProperty.keyTime(m) * 10000) / 10000,
                        comment: mv.comment,
                        duration: mv.duration
                    }});
                }}
            }}
        }} catch (eM) {{}}

        return {{
            id: comp.id,
            name: comp.name,
            width: comp.width,
            height: comp.height,
            frameRate: Math.round(comp.frameRate * 10000) / 10000,
            duration: Math.round(comp.duration * 10000) / 10000,
            workAreaStart: Math.round(comp.workAreaStart * 10000) / 10000,
            workAreaDuration: Math.round(comp.workAreaDuration * 10000) / 10000,
            currentTime: Math.round(comp.time * 10000) / 10000,
            currentFrame: Math.round(comp.time * comp.frameRate),
            bgColor: comp.bgColor,
            numLayers: comp.numLayers,
            markers: markers,
            layers: layers
        }};
        """,
        undo_name=None,
    )


@mcp.tool()
async def ae_inspect_layer_properties(
    layer_index_or_name: Union[int, str],
    comp_name_or_id: Optional[str] = None,
    property_path: Optional[str] = None,
    max_depth: int = 3,
    include_keyframes: bool = True,
) -> Dict[str, Any]:
    """
    Recorre el árbol de propiedades de una capa (ej. 'Transform', 'Effects', 'Text', 'Contents',
    o cualquier matchName como 'ADBE Effect Parade.1') devolviendo valores actuales,
    matchNames exactos, expresiones y keyframes.
    """
    comp_js = json.dumps(comp_name_or_id) if comp_name_or_id else "null"
    lyr_js = json.dumps(layer_index_or_name)
    prop_js = json.dumps(property_path) if property_path else "null"
    kf_js = "true" if include_keyframes else "false"

    return await execute_in_ae(
        f"""
        var comp = AEMCP.findComp({comp_js});
        if (!comp) throw new Error("No se encontró la composición.");
        var lyr = AEMCP.findLayer(comp, {lyr_js});
        if (!lyr) throw new Error("No se encontró la capa: " + {lyr_js});

        var targetProp = lyr;
        if ({prop_js} !== null && {prop_js} !== "") {{
            targetProp = AEMCP.resolveProperty(lyr, {prop_js});
            if (!targetProp) throw new Error("No se encontró la propiedad: " + {prop_js});
        }}

        return {{
            compName: comp.name,
            layerIndex: lyr.index,
            layerName: lyr.name,
            propertyTree: AEMCP.serializePropertyTree(targetProp, 0, {int(max_depth)}, {kf_js})
        }};
        """,
        undo_name=None,
    )


@mcp.tool()
async def ae_list_installed_effects(
    search_query: Optional[str] = None,
    category_filter: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Busca entre todos los efectos y plugins instalados en After Effects v27.0
    devolviendo su `displayName`, `matchName` exacto y `category`.
    """
    q_js = json.dumps(search_query.lower()) if search_query else "null"
    cat_js = json.dumps(category_filter.lower()) if category_filter else "null"

    return await execute_in_ae(
        f"""
        var query = {q_js};
        var catFilter = {cat_js};
        var maxResults = {int(limit)};
        var matches = [];
        var total = app.effects ? app.effects.length : 0;

        for (var i = 0; i < total; i++) {{
            var fx = app.effects[i];
            if (fx.category === "") continue;
            var dName = String(fx.displayName || "");
            var mName = String(fx.matchName || "");
            var cat = String(fx.category || "");

            if (query && dName.toLowerCase().indexOf(query) === -1 && mName.toLowerCase().indexOf(query) === -1) {{
                continue;
            }}
            if (catFilter && cat.toLowerCase().indexOf(catFilter) === -1) {{
                continue;
            }}
            matches.push({{
                displayName: dName,
                matchName: mName,
                category: cat,
                version: fx.version
            }});
            if (matches.length >= maxResults) break;
        }}
        return {{
            totalEffectsInstalled: total,
            returnedCount: matches.length,
            effects: matches
        }};
        """,
        undo_name=None,
    )


@mcp.tool()
async def ae_save_or_backup(
    save_project: bool = True,
    save_as_path: Optional[str] = None,
    create_timestamped_aep_copy: bool = False,
    snapshot_comp_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Herramienta de seguridad:
    - Puede duplicar una composición en la carpeta `_MCP_SNAPSHOTS` antes de editarla.
    - Puede guardar el proyecto `.aep` actual o guardar una copia versionada en disco.
    """
    save_js = "true" if save_project else "false"
    save_as_js = json.dumps(str(Path(save_as_path).resolve()).replace("\\", "/")) if save_as_path else "null"
    copy_js = "true" if create_timestamped_aep_copy else "false"
    snap_js = json.dumps(snapshot_comp_name) if snapshot_comp_name else "null"

    return await execute_in_ae(
        f"""
        var out = {{}};
        if ({snap_js} !== null) {{
            var comp = AEMCP.findComp({snap_js} === "__ACTIVE__" ? null : {snap_js});
            if (!comp) throw new Error("No se encontró la composición para snapshot: " + {snap_js});
            out.compSnapshot = AEMCP.backupComp(comp);
        }}

        if ({save_as_js} !== null) {{
            var targetFile = new File({save_as_js});
            app.project.save(targetFile);
            out.savedTo = targetFile.fsName;
        }} else if ({save_js} && app.project.file) {{
            app.project.save();
            out.savedTo = app.project.file.fsName;
        }}

        if ({copy_js} && app.project.file) {{
            var origPath = app.project.file.fsName.replace(/\\\\/g, "/");
            var dotIdx = origPath.lastIndexOf(".");
            var base = dotIdx > 0 ? origPath.substring(0, dotIdx) : origPath;
            var stamp = new Date().getTime();
            var backupFile = new File(base + "_MCP_BACKUP_" + stamp + ".aep");
            var currentFile = app.project.file;
            app.project.save(backupFile);
            app.project.save(currentFile);
            out.timestampedBackupCopy = backupFile.fsName;
        }}
        return out;
        """,
        undo_name="MCP Save / Snapshot",
    )


@mcp.tool()
async def ae_create_composition(
    name: str,
    width: int = 1920,
    height: int = 1080,
    fps: float = 24.0,
    duration: float = 30.0,
    bg_color_rgb: Optional[List[float]] = None,
    open_in_viewer: bool = True,
) -> Dict[str, Any]:
    """
    Crea una nueva composición en After Effects con la resolución, FPS, duración
    y color de fondo indicados ([R, G, B] en rango 0.0 a 1.0).
    """
    bg = bg_color_rgb if (bg_color_rgb and len(bg_color_rgb) == 3) else [0.05, 0.05, 0.05]
    open_js = "true" if open_in_viewer else "false"

    return await execute_in_ae(
        f"""
        var comp = app.project.items.addComp(
            {json.dumps(name)},
            {int(width)},
            {int(height)},
            1.0,
            {float(duration)},
            {float(fps)}
        );
        comp.bgColor = {json.dumps(bg)};
        if ({open_js}) {{
            comp.openInViewer();
        }}
        return {{
            id: comp.id,
            name: comp.name,
            width: comp.width,
            height: comp.height,
            frameRate: comp.frameRate,
            duration: comp.duration
        }};
        """,
        undo_name=f"MCP Create Comp: {name}",
    )


@mcp.tool()
async def ae_import_media(
    file_paths: List[str],
    target_folder_name: str = "MCP_Imports",
    add_to_comp: Optional[str] = None,
    sequence: bool = False,
) -> Dict[str, Any]:
    """
    Importa uno o varios archivos (videos, audios, imágenes, .aep) a una carpeta del proyecto,
    y opcionalmente los agrega como capas a una composición.
    """
    norm_paths = [str(Path(p).resolve()).replace("\\", "/") for p in file_paths]
    seq_js = "true" if sequence else "false"
    comp_js = json.dumps(add_to_comp) if add_to_comp else "null"

    return await execute_in_ae(
        f"""
        var paths = {json.dumps(norm_paths)};
        var folder = AEMCP.getOrCreateFolder({json.dumps(target_folder_name)});
        var comp = ({comp_js} !== null) ? AEMCP.findComp({comp_js}) : null;
        var imported = [];

        for (var i = 0; i < paths.length; i++) {{
            var f = new File(paths[i]);
            if (!f.exists) {{
                imported.push({{ path: paths[i], ok: false, error: "File does not exist" }});
                continue;
            }}
            var io = new ImportOptions(f);
            io.sequence = {seq_js};
            var item = app.project.importFile(io);
            item.parentFolder = folder;
            var rec = {{
                path: paths[i],
                ok: true,
                itemId: item.id,
                name: item.name,
                duration: item.duration || 0
            }};
            if (comp) {{
                var lyr = comp.layers.add(item);
                rec.addedLayerIndex = lyr.index;
            }}
            imported.push(rec);
        }}
        return {{
            folder: folder.name,
            importedCount: imported.length,
            items: imported
        }};
        """,
        undo_name="MCP Import Media",
    )


@mcp.tool()
async def ae_manage_layers(
    comp_name_or_id: Optional[str],
    operations: List[Dict[str, Any]],
    auto_backup_comp: bool = False,
) -> Dict[str, Any]:
    """
    Crea o modifica múltiples capas en una sola transacción (un único Undo Group).
    Cada elemento de `operations` es un dict con `action`:
    - `create_text`: {name, text, fontSize, fillColor:[r,g,b], position:[x,y], inPoint, outPoint}
    - `create_solid`: {name, color:[r,g,b], width, height, duration, isAdjustmentLayer}
    - `create_null`: {name, threeDLayer}
    - `create_shape`: {name}
    - `create_camera`: {name, centerPoint:[x,y], zoom}
    - `create_light`: {name, lightType, intensity, color:[r,g,b]}
    - `add_project_item`: {itemNameOrId, startTime, inPoint, outPoint}
    - `update`: {layer (index o nombre), name, startTime, inPoint, outPoint, enabled, solo, locked, threeDLayer, blendingMode, stretch, parentLayer, moveBeforeIndex, moveToEnd}
    - `duplicate`: {layer (index o nombre), newName}
    - `delete`: {layer (index o nombre)}
    """
    comp_js = json.dumps(comp_name_or_id) if comp_name_or_id else "null"
    ops_js = json.dumps(operations)

    return await execute_in_ae(
        f"""
        var comp = AEMCP.findComp({comp_js});
        if (!comp) throw new Error("No se encontró la composición objetivo.");
        var ops = {ops_js};
        var results = [];

        for (var i = 0; i < ops.length; i++) {{
            var op = ops[i];
            var act = String(op.action || "update").toLowerCase();
            var lyr = null;

            if (act === "create_text") {{
                lyr = comp.layers.addText(String(op.text || ""));
                if (op.name) lyr.name = String(op.name);
                var textProp = lyr.property("ADBE Text Properties").property("ADBE Text Document");
                var td = textProp.value;
                if (op.fontSize !== undefined) td.fontSize = Number(op.fontSize);
                if (op.font !== undefined) td.font = String(op.font);
                if (op.fillColor !== undefined) {{
                    td.applyFill = true;
                    td.fillColor = op.fillColor;
                }}
                if (op.strokeColor !== undefined) {{
                    td.applyStroke = true;
                    td.strokeColor = op.strokeColor;
                }}
                textProp.setValue(td);
            }} else if (act === "create_solid") {{
                var col = op.color || [0.0, 0.0, 0.0];
                var w = op.width || comp.width;
                var h = op.height || comp.height;
                var dur = op.duration || comp.duration;
                var sName = op.name || (op.isAdjustmentLayer ? "Adjustment Layer" : "Solid");
                lyr = comp.layers.addSolid(col, sName, w, h, 1.0, dur);
                if (op.isAdjustmentLayer) {{
                    lyr.adjustmentLayer = true;
                }}
            }} else if (act === "create_null") {{
                lyr = comp.layers.addNull(op.duration || comp.duration);
                if (op.name) lyr.name = String(op.name);
                if (op.threeDLayer !== undefined) lyr.threeDLayer = Boolean(op.threeDLayer);
            }} else if (act === "create_shape") {{
                lyr = comp.layers.addShape();
                if (op.name) lyr.name = String(op.name);
            }} else if (act === "create_camera") {{
                var cp = op.centerPoint || [comp.width / 2, comp.height / 2];
                lyr = comp.layers.addCamera(op.name || "MCP Camera", cp);
            }} else if (act === "create_light") {{
                var lcp = op.centerPoint || [comp.width / 2, comp.height / 2];
                lyr = comp.layers.addLight(op.name || "MCP Light", lcp);
            }} else if (act === "add_project_item") {{
                var targetItem = null;
                var query = op.itemNameOrId;
                for (var k = 1; k <= app.project.numItems; k++) {{
                    var it = app.project.item(k);
                    if (it.id === Number(query) || it.name === String(query)) {{
                        targetItem = it;
                        break;
                    }}
                }}
                if (!targetItem) throw new Error("No se encontró el item de proyecto: " + query);
                lyr = comp.layers.add(targetItem);
            }} else if (act === "duplicate") {{
                var srcLyr = AEMCP.findLayer(comp, op.layer);
                if (!srcLyr) throw new Error("No se encontró capa para duplicar: " + op.layer);
                lyr = srcLyr.duplicate();
                if (op.newName) lyr.name = String(op.newName);
            }} else if (act === "delete") {{
                var delLyr = AEMCP.findLayer(comp, op.layer);
                if (!delLyr) throw new Error("No se encontró capa para eliminar: " + op.layer);
                var delIdx = delLyr.index;
                var delName = delLyr.name;
                delLyr.remove();
                results.push({{ action: "delete", removedIndex: delIdx, removedName: delName }});
                continue;
            }} else {{
                lyr = AEMCP.findLayer(comp, op.layer);
                if (!lyr) throw new Error("No se encontró la capa: " + op.layer);
            }}

            // Apply common layer modifications
            if (lyr) {{
                if (op.name !== undefined && act === "update") lyr.name = String(op.name);
                if (op.enabled !== undefined) lyr.enabled = Boolean(op.enabled);
                if (op.solo !== undefined) lyr.solo = Boolean(op.solo);
                if (op.shy !== undefined) lyr.shy = Boolean(op.shy);
                if (op.locked !== undefined) lyr.locked = Boolean(op.locked);
                if (op.threeDLayer !== undefined) lyr.threeDLayer = Boolean(op.threeDLayer);
                if (op.stretch !== undefined) lyr.stretch = Number(op.stretch);
                if (op.startTime !== undefined) lyr.startTime = Number(op.startTime);
                if (op.inPoint !== undefined) lyr.inPoint = Number(op.inPoint);
                if (op.outPoint !== undefined) lyr.outPoint = Number(op.outPoint);
                if (op.label !== undefined) lyr.label = Number(op.label);

                if (op.position !== undefined) {{
                    lyr.property("ADBE Transform Group").property("ADBE Position").setValue(op.position);
                }}
                if (op.scale !== undefined) {{
                    lyr.property("ADBE Transform Group").property("ADBE Scale").setValue(op.scale);
                }}
                if (op.opacity !== undefined) {{
                    lyr.property("ADBE Transform Group").property("ADBE Opacity").setValue(Number(op.opacity));
                }}
                if (op.rotation !== undefined) {{
                    lyr.property("ADBE Transform Group").property("ADBE Rotate Z").setValue(Number(op.rotation));
                }}
                if (op.blendingMode !== undefined && typeof BlendingMode[op.blendingMode] !== "undefined") {{
                    lyr.blendingMode = BlendingMode[op.blendingMode];
                }}
                if (op.parentLayer !== undefined) {{
                    if (op.parentLayer === null) {{
                        lyr.parent = null;
                    }} else {{
                        var pLyr = AEMCP.findLayer(comp, op.parentLayer);
                        if (pLyr) lyr.parent = pLyr;
                    }}
                }}
                if (op.moveToBeginning) {{
                    lyr.moveToBeginning();
                }} else if (op.moveToEnd) {{
                    lyr.moveToEnd();
                }} else if (op.moveBeforeIndex !== undefined) {{
                    var refLyr = comp.layer(Number(op.moveBeforeIndex));
                    if (refLyr) lyr.moveBefore(refLyr);
                }}

                results.push({{
                    action: act,
                    layerIndex: lyr.index,
                    layerName: lyr.name,
                    inPoint: Math.round(lyr.inPoint * 1000) / 1000,
                    outPoint: Math.round(lyr.outPoint * 1000) / 1000
                }});
            }}
        }}

        return {{
            compName: comp.name,
            operationsApplied: results.length,
            results: results
        }};
        """,
        undo_name="MCP Manage Layers",
        auto_backup_comp=(comp_name_or_id or "__ACTIVE__") if auto_backup_comp else None,
    )


@mcp.tool()
async def ae_set_property_or_keyframes(
    layer_index_or_name: Union[int, str],
    property_path: str,
    comp_name_or_id: Optional[str] = None,
    value: Optional[Any] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
    clear_existing_keyframes: bool = False,
    expression: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Configura el valor estático, los keyframes o la expresión de cualquier propiedad de una capa.
    - `property_path`: ej. 'Transform.Position', 'Transform.Opacity', 'Transform.Scale',
      'Effects.Gaussian Blur.Blurriness', o con matchNames ('ADBE Transform Group.ADBE Opacity').
    - `keyframes`: lista de `{time: float_seconds, value: any, easing: 'LINEAR'|'BEZIER'|'HOLD'|'EASY_EASE'}`.
    - `expression`: string con expresión JS/ExtendScript (verifica automáticamente si hay error de expresión).
    """
    comp_js = json.dumps(comp_name_or_id) if comp_name_or_id else "null"
    lyr_js = json.dumps(layer_index_or_name)
    path_js = json.dumps(property_path)
    val_js = json.dumps(value) if value is not None else "undefined"
    kfs_js = json.dumps(keyframes) if keyframes is not None else "null"
    clr_js = "true" if clear_existing_keyframes else "false"
    expr_js = json.dumps(expression) if expression is not None else "null"

    return await execute_in_ae(
        f"""
        var comp = AEMCP.findComp({comp_js});
        if (!comp) throw new Error("No se encontró la composición.");
        var lyr = AEMCP.findLayer(comp, {lyr_js});
        if (!lyr) throw new Error("No se encontró la capa: " + {lyr_js});
        var prop = AEMCP.resolveProperty(lyr, {path_js});
        if (!prop) throw new Error("No se encontró la propiedad '" + {path_js} + "' en la capa '" + lyr.name + "'.");

        if ({clr_js} && prop.numKeys > 0) {{
            for (var r = prop.numKeys; r >= 1; r--) {{
                prop.removeKey(r);
            }}
        }}

        if ({val_js} !== undefined && ({kfs_js} === null || {kfs_js}.length === 0)) {{
            if (prop.numKeys > 0) {{
                prop.setValueAtTime(comp.time, {val_js});
            }} else {{
                prop.setValue({val_js});
            }}
        }}

        if ({kfs_js} !== null && {kfs_js}.length > 0) {{
            var kList = {kfs_js};
            for (var i = 0; i < kList.length; i++) {{
                var kf = kList[i];
                var t = Number(kf.time);
                prop.setValueAtTime(t, kf.value);
            }}
            for (var j = 0; j < kList.length; j++) {{
                var kf2 = kList[j];
                var easing = String(kf2.easing || "").toUpperCase();
                var kIdx = prop.nearestKeyIndex(Number(kf2.time));
                if (easing === "HOLD") {{
                    prop.setInterpolationTypeAtKey(kIdx, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.HOLD);
                }} else if (easing === "LINEAR") {{
                    prop.setInterpolationTypeAtKey(kIdx, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
                }} else if (easing === "BEZIER" || easing === "EASY_EASE") {{
                    prop.setInterpolationTypeAtKey(kIdx, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
                    if (easing === "EASY_EASE") {{
                        try {{
                            var easeIn = new KeyframeEase(0, 33.33);
                            var easeOut = new KeyframeEase(0, 33.33);
                            var dims = 1;
                            if (prop.propertyValueType === PropertyValueType.TwoD_SPATIAL || prop.propertyValueType === PropertyValueType.OneD) {{
                                dims = 1;
                            }} else if (prop.propertyValueType === PropertyValueType.TwoD) {{
                                dims = 2;
                            }} else if (prop.propertyValueType === PropertyValueType.ThreeD) {{
                                dims = 3;
                            }}
                            var inArr = [], outArr = [];
                            for (var d = 0; d < dims; d++) {{
                                inArr.push(easeIn);
                                outArr.push(easeOut);
                            }}
                            prop.setTemporalEaseAtKey(kIdx, inArr, outArr);
                        }} catch (eEase) {{}}
                    }}
                }}
            }}
        }}

        var exprError = null;
        if ({expr_js} !== null) {{
            if (prop.canSetExpression) {{
                prop.expression = {expr_js};
                prop.expressionEnabled = ({expr_js} !== "");
                exprError = prop.expressionError || null;
            }} else {{
                throw new Error("La propiedad '" + prop.name + "' no admite expresiones.");
            }}
        }}

        return {{
            compName: comp.name,
            layerName: lyr.name,
            propertyName: prop.name,
            matchName: prop.matchName,
            currentValue: AEMCP.safePropValue(prop),
            numKeys: prop.numKeys,
            expression: prop.expression || "",
            expressionError: exprError
        }};
        """,
        undo_name=f"MCP Set {property_path}",
    )


@mcp.tool()
async def ae_apply_or_update_effect(
    layer_index_or_name: Union[int, str],
    effect_name_or_match_name: str,
    params: Optional[Dict[str, Any]] = None,
    effect_instance_name: Optional[str] = None,
    comp_name_or_id: Optional[str] = None,
    reuse_existing: bool = True,
) -> Dict[str, Any]:
    """
    Aplica un efecto (por `matchName` o `displayName`) a una capa y configura sus parámetros.
    Si `reuse_existing=True` y el efecto ya está en la capa, actualiza sus parámetros sin duplicarlo.
    """
    comp_js = json.dumps(comp_name_or_id) if comp_name_or_id else "null"
    lyr_js = json.dumps(layer_index_or_name)
    fx_js = json.dumps(effect_name_or_match_name)
    inst_js = json.dumps(effect_instance_name) if effect_instance_name else "null"
    params_js = json.dumps(params or {})
    reuse_js = "true" if reuse_existing else "false"

    return await execute_in_ae(
        f"""
        var comp = AEMCP.findComp({comp_js});
        if (!comp) throw new Error("No se encontró la composición.");
        var lyr = AEMCP.findLayer(comp, {lyr_js});
        if (!lyr) throw new Error("No se encontró la capa: " + {lyr_js});

        var fxParade = lyr.property("ADBE Effect Parade");
        if (!fxParade) throw new Error("La capa '" + lyr.name + "' no soporta efectos.");

        var fxName = {fx_js};
        var fxProp = null;

        if ({reuse_js}) {{
            for (var i = 1; i <= fxParade.numProperties; i++) {{
                var candidate = fxParade.property(i);
                if (candidate.matchName === fxName || candidate.name === fxName || ({inst_js} && candidate.name === {inst_js})) {{
                    fxProp = candidate;
                    break;
                }}
            }}
        }}

        if (!fxProp) {{
            fxProp = fxParade.addProperty(fxName);
        }}
        if (!fxProp) throw new Error("No se pudo agregar el efecto: " + fxName);

        if ({inst_js} !== null) {{
            fxProp.name = {inst_js};
        }}

        var paramUpdates = {params_js};
        var appliedParams = [];
        for (var pKey in paramUpdates) {{
            if (paramUpdates.hasOwnProperty(pKey)) {{
                var targetP = null;
                try {{
                    if (/^\\d+$/.test(String(pKey))) {{
                        targetP = fxProp.property(parseInt(pKey, 10));
                    }} else {{
                        targetP = fxProp.property(String(pKey));
                    }}
                }} catch (e1) {{}}
                if (!targetP) {{
                    var lowerK = String(pKey).toLowerCase();
                    for (var m = 1; m <= fxProp.numProperties; m++) {{
                        var sub = fxProp.property(m);
                        if (sub.name.toLowerCase() === lowerK || sub.matchName.toLowerCase() === lowerK) {{
                            targetP = sub;
                            break;
                        }}
                    }}
                }}
                if (targetP) {{
                    targetP.setValue(paramUpdates[pKey]);
                    appliedParams.push({{
                        name: targetP.name,
                        matchName: targetP.matchName,
                        value: AEMCP.safePropValue(targetP)
                    }});
                }} else {{
                    appliedParams.push({{ name: pKey, error: "Parameter not found" }});
                }}
            }}
        }}

        return {{
            compName: comp.name,
            layerName: lyr.name,
            effectName: fxProp.name,
            effectMatchName: fxProp.matchName,
            effectIndex: fxProp.propertyIndex,
            updatedParams: appliedParams
        }};
        """,
        undo_name=f"MCP Effect: {effect_name_or_match_name}",
    )


@mcp.tool()
async def ae_capture_frame_preview(
    comp_name_or_id: Optional[str] = None,
    time_seconds: Optional[float] = None,
    output_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Renderiza un frame de la composición (en el segundo `time_seconds` o donde esté el cabezal)
    a un archivo PNG en disco y devuelve su ruta absoluta para que la IA pueda verlo con `read_file`.
    """
    comp_js = json.dumps(comp_name_or_id) if comp_name_or_id else "null"
    time_js = str(float(time_seconds)) if time_seconds is not None else "null"
    fname = output_filename or f"preview_{int(time.time() * 1000)}.png"
    if not fname.lower().endswith(".png"):
        fname += ".png"
    out_path = (PREVIEW_DIR / fname).resolve()
    out_path_js = str(out_path).replace("\\", "/")

    res = await execute_in_ae(
        f"""
        var comp = AEMCP.findComp({comp_js});
        if (!comp) throw new Error("No se encontró la composición para capturar preview.");

        var captureTime = ({time_js} !== null) ? Number({time_js}) : comp.time;
        var outFile = new File({json.dumps(out_path_js)});
        if (outFile.exists) outFile.remove();

        var okSaved = comp.saveFrameToPng(captureTime, outFile);
        return {{
            saved: okSaved,
            fileExists: outFile.exists,
            previewPath: outFile.fsName,
            compName: comp.name,
            capturedTimeSeconds: Math.round(captureTime * 1000) / 1000,
            capturedFrame: Math.round(captureTime * comp.frameRate),
            resolution: [comp.width, comp.height]
        }};
        """,
        undo_name=None,
        timeout_seconds=30.0,
    )

    # En AE 2024-2027 saveFrameToPng es asíncrono; esperamos a que termine de escribir el PNG en disco
    if res.get("ok") and isinstance(res.get("result"), dict):
        for _ in range(50):
            if out_path.exists() and out_path.stat().st_size > 0:
                res["result"]["fileExists"] = True
                res["result"]["fileSizeBytes"] = out_path.stat().st_size
                break
            await asyncio.sleep(0.1)

    return res


@mcp.tool()
async def ae_execute_jsx(
    jsx_code: str,
    undo_group_name: Optional[str] = "MCP Custom JSX",
    auto_backup_comp: Optional[str] = None,
    suppress_dialogs: bool = True,
    timeout_seconds: float = 45.0,
) -> Dict[str, Any]:
    """
    Ejecuta código ExtendScript (.jsx) personalizado adentro de After Effects v27.0.
    - Tenés disponible el objeto `AEMCP` (`AEMCP.findComp()`, `AEMCP.findLayer()`, `AEMCP.backupComp()`,
      `AEMCP.resolveProperty()`, `AEMCP.serializeLayer()`).
    - Usá `return { ... };` al final de tu código para devolver cualquier estructura JSON a Python.
    - Todo corre dentro de un `app.beginUndoGroup` y `try/catch` seguro.
    """
    return await execute_in_ae(
        jsx_body=jsx_code,
        undo_name=undo_group_name,
        suppress_dialogs=suppress_dialogs,
        auto_backup_comp=auto_backup_comp,
        timeout_seconds=timeout_seconds,
    )


if __name__ == "__main__":
    try:
        ensure_ae_disk_permissions()
    except Exception:
        pass
    mcp.run()
