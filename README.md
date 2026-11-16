# 🎬 After Effects Pro MCP Server (`fastmcp`)

Servidor **MCP (Model Context Protocol)** de nivel estudio construido con [FastMCP](https://github.com/PrefectHQ/fastmcp) para controlar **Adobe After Effects (2024 / 2025 / 2026 / 2027+)** directamente desde agentes de IA como **Google Antigravity**, **Cursor** o **Claude Desktop**.

---

## ✨ Características Principales

* **🔍 Autodetección Universal de After Effects:** Detecta automáticamente cualquier versión instalada de After Effects en Windows (`2024`, `2025`, `2026`, `2027+`) o la instancia que esté corriendo en vivo en ese momento.
* **🛡️ Protección `Ctrl + Z` Automática (`Undo Group`):** Cada acción ejecutada por la IA se envuelve automáticamente en `app.beginUndoGroup()`, permitiendo deshacer cualquier cambio complejo con un solo `Ctrl + Z`.
* **📸 Snapshots Anti-Roturas (`_MCP_SNAPSHOTS`):** Permite clonar composiciones automáticamente dentro del proyecto antes de realizar ediciones estructurales.
* **👁️ Visión en Vivo (`ae_capture_frame_preview`):** Renderiza instantáneamente el cuadro actual de la composición a `.png` para que la IA pueda ver cómo está quedando el diseño, color y tipografía.
* **🔓 Auto-Permisos y Panel Acoplable:** Activa automáticamente `Pref_SCRIPTING_FILE_NETWORK_SECURITY = 1` (*"Permitir que los scripts puedan escribir archivos y acceder a la red"*) e instala el panel nativo `AE_MCP_Pro_Panel.jsx` en el menú `Ventana` de After Effects.

---

## 🚀 Instalación en 1 Clic (Plug & Play)

1. Cloná este repositorio:
   ```bash
   git clone https://github.com/rar-77/after-effects-mcp.git
   cd after-effects-mcp
   ```
2. Hacé **doble clic en `install.bat`** (o corré `install.bat` desde la terminal).
   *El instalador automático se encarga de:*
   * Crear el entorno virtual `.venv` e instalar `fastmcp` y `psutil`.
   * Detectar todas tus versiones de After Effects instaladas.
   * Habilitar los permisos de scripting e instalar el panel `AE_MCP_Pro_Panel.jsx`.
   * Registrar automáticamente el servidor `after-effects-pro` en **Antigravity** (`~/.gemini/config/mcp_config.json`), **Cursor** y **Claude Desktop**.

---

## 🛠️ Las 14 Herramientas Incluidas

| Herramienta | Descripción |
| :--- | :--- |
| `ae_status` | Verifica si After Effects está abierto, consumo de RAM, ruta del ejecutable, proyecto y composición activa. |
| `ae_launch_and_setup` | Inicia After Effects si está cerrado, configura permisos y abre cualquier archivo `.aep`. |
| `ae_get_project_overview` | Devuelve el mapa completo del proyecto: composiciones, carpetas y archivos de footage importados. |
| `ae_inspect_composition` | Inspecciona todas las capas de una composición (`inPoint`, `outPoint`, `startTime`, `transform`, `effects`, `text`, `parent`). |
| `ae_inspect_layer_properties` | Recorre el árbol profundo de propiedades de una capa (`matchName`, valores actuales, expresiones y keyframes). |
| `ae_list_installed_effects` | Lista y busca entre todos los efectos y plugins de terceros instalados en tu After Effects. |
| `ae_save_or_backup` | Guarda el proyecto `.aep`, crea copias `.aep` con timestamp en disco o snapshots en `_MCP_SNAPSHOTS`. |
| `ae_create_composition` | Crea nuevas composiciones con resolución, FPS, duración y color de fondo personalizados. |
| `ae_import_media` | Importa videos, audios, imágenes o secuencias organizadas en carpetas y las agrega a la composición. |
| `ae_manage_layers` | Crea o edita múltiples capas en lote (Textos, Sólidos, Adjustment Layers, Nulls, Cámaras, Luces, Shapes, tiempos y cortes). |
| `ae_set_property_or_keyframes` | Aplica valores estáticos, curvas de keyframes (`LINEAR`, `BEZIER`, `HOLD`, `EASY_EASE`) y expresiones validando errores. |
| `ae_apply_or_update_effect` | Aplica cualquier efecto por nombre o `matchName` y ajusta todos sus parámetros en un solo paso. |
| `ae_capture_frame_preview` | Renderiza el cuadro actual de la composición a `.png` para inspección visual directa por parte de la IA. |
| `ae_execute_jsx` | Ejecuta código ExtendScript (`.jsx`) arbitrario con retorno JSON directo y protección `Undo Group`. |

---

## 📂 Estructura del Proyecto

```text
after_effects_mcp/
├── server.py                      # Servidor principal FastMCP (14 herramientas + IPC Bridge)
├── setup_installer.py             # Autoconfigurador universal multi-versión y multi-editor
├── install.bat                    # Instalador 1-clic para Windows
├── requirements.txt               # Dependencias de Python (fastmcp, psutil)
└── jsx/
    ├── ae_mcp_runtime.jsx         # Motor ExtendScript ES3 (JSON polyfill, DOM traversal, Snapshots)
    ├── AE_MCP_Pro_Panel.jsx       # Panel acoplable nativo para After Effects (Ventana > AE_MCP_Pro_Panel)
    └── AE_MCP_AutoPermissions.jsx # Script Startup que habilita permisos automáticamente
```
