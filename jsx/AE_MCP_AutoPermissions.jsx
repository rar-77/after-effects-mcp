/*
================================================================================
  AE MCP STARTUP PERMISSIONS ENABLER (After Effects v27.0)
  Se ejecuta automáticamente al iniciar After Effects 27.0 para garantizar que
  el puente FastMCP tenga permisos de lectura/escritura de respuestas JSON.
================================================================================
*/
(function () {
    try {
        app.preferences.savePrefAsLong("Main Pref Section v2", "Pref_SCRIPTING_FILE_NETWORK_SECURITY", 1);
        app.preferences.saveToDisk();
    } catch (e) {}
})();
