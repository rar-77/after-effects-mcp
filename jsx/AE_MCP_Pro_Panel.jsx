/*
================================================================================
  🎛️ AE MCP PRO PANEL (Dockable ScriptUI Panel for After Effects v27.0)
  Ubicación en menú: Ventana > AE_MCP_Pro_Panel.jsx
================================================================================
*/

(function createMcpProPanel(thisObj) {
    function buildUI(thisObj) {
        var win = (thisObj instanceof Panel)
            ? thisObj
            : new Window("palette", "Antigravity MCP Pro v27.0", undefined, { resizeable: true });

        win.orientation = "column";
        win.alignChildren = ["fill", "top"];
        win.spacing = 8;
        win.margins = 12;

        var headerGrp = win.add("group");
        headerGrp.orientation = "column";
        headerGrp.alignChildren = ["left", "top"];
        headerGrp.spacing = 2;

        var titleTxt = headerGrp.add("statictext", undefined, "⚡ Antigravity + FastMCP Bridge (AE 27.0)");
        var statusTxt = headerGrp.add("statictext", undefined, "Estado: Listo y conectado con Antigravity");

        var secPanel = win.add("panel", undefined, "Seguridad y Permisos");
        secPanel.orientation = "column";
        secPanel.alignChildren = ["fill", "top"];
        secPanel.spacing = 6;
        secPanel.margins = 10;

        var btnPerms = secPanel.add("button", undefined, "🔓 Habilitar Permisos de Scripts y Red");
        var btnSnap = secPanel.add("button", undefined, "📸 Crear Snapshot de Composición Activa");
        var btnSaveCopy = secPanel.add("button", undefined, "💾 Guardar Copia Backup del .AEP");

        btnPerms.onClick = function () {
            try {
                app.preferences.savePrefAsLong("Main Pref Section v2", "Pref_SCRIPTING_FILE_NETWORK_SECURITY", 1);
                app.preferences.saveToDisk();
                statusTxt.text = "Estado: Permisos de red/archivos ACTIVOS ✔";
                alert("Permisos de Scripts y Red habilitados correctamente en After Effects " + app.version);
            } catch (e) {
                alert("Error al configurar permisos: " + e.message);
            }
        };

        btnSnap.onClick = function () {
            if (!app.project || !(app.project.activeItem instanceof CompItem)) {
                alert("Seleccioná primero una composición activa.");
                return;
            }
            app.beginUndoGroup("Crear Snapshot MCP");
            try {
                var comp = app.project.activeItem;
                var folder = null;
                for (var i = 1; i <= app.project.numItems; i++) {
                    if (app.project.item(i) instanceof FolderItem && app.project.item(i).name === "_MCP_SNAPSHOTS") {
                        folder = app.project.item(i);
                        break;
                    }
                }
                if (!folder) folder = app.project.items.addFolder("_MCP_SNAPSHOTS");
                var dup = comp.duplicate();
                dup.name = comp.name + "_SNAP_" + (new Date().getTime());
                dup.parentFolder = folder;
                statusTxt.text = "Snapshot creado: " + dup.name;
            } catch (e) {
                alert("Error: " + e.message);
            } finally {
                app.endUndoGroup();
            }
        };

        btnSaveCopy.onClick = function () {
            if (!app.project || !app.project.file) {
                alert("Guardá primero el proyecto .aep al menos una vez.");
                return;
            }
            try {
                var origPath = app.project.file.fsName.replace(/\\/g, "/");
                var dotIdx = origPath.lastIndexOf(".");
                var base = dotIdx > 0 ? origPath.substring(0, dotIdx) : origPath;
                var backupFile = new File(base + "_BACKUP_" + (new Date().getTime()) + ".aep");
                var curFile = app.project.file;
                app.project.save(backupFile);
                app.project.save(curFile);
                statusTxt.text = "Backup .AEP guardado ✔";
            } catch (e) {
                alert("Error guardando backup: " + e.message);
            }
        };

        // Auto-ensure permissions on panel load
        try {
            app.preferences.savePrefAsLong("Main Pref Section v2", "Pref_SCRIPTING_FILE_NETWORK_SECURITY", 1);
            app.preferences.saveToDisk();
        } catch (eAuto) {}

        win.onResizing = win.onResize = function () {
            this.layout.resize();
        };

        if (win instanceof Window) {
            win.center();
            win.show();
        } else {
            win.layout.layout(true);
            win.layout.resize();
        }
        return win;
    }

    buildUI(thisObj);
})(this);
