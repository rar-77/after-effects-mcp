/*
================================================================================
  AE MCP PRO RUNTIME (ExtendScript ES3 Engine for After Effects v27.0+)
  Provides JSON serialization, safe DOM traversal, automatic undo & snapshots,
  property path resolution, and error-proof inspection.
================================================================================
*/

if (typeof JSON === "undefined") {
    JSON = {};
}

(function () {
    function f(n) {
        return n < 10 ? "0" + n : n;
    }
    var escapable = /[\\\"\x00-\x1f\x7f-\x9f\u00ad\u0600-\u0604\u070f\u17b4\u17b5\u200c-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufff0-\uffff]/g;
    var meta = {
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
        "\"": "\\\"",
        "\\": "\\\\"
    };
    function quote(string) {
        escapable.lastIndex = 0;
        return escapable.test(string) ? "\"" + string.replace(escapable, function (a) {
            var c = meta[a];
            return typeof c === "string" ? c : "\\u" + ("0000" + a.charCodeAt(0).toString(16)).slice(-4);
        }) + "\"" : "\"" + string + "\"";
    }
    function str(key, holder) {
        var i, k, v, length, partial, value = holder[key];
        if (value && typeof value === "object" && typeof value.toJSON === "function") {
            value = value.toJSON(key);
        }
        switch (typeof value) {
            case "string":
                return quote(value);
            case "number":
                return isFinite(value) ? String(value) : "null";
            case "boolean":
            case "null":
                return String(value);
            case "object":
                if (!value) {
                    return "null";
                }
                partial = [];
                if (Object.prototype.toString.apply(value) === "[object Array]") {
                    length = value.length;
                    for (i = 0; i < length; i += 1) {
                        partial[i] = str(i, value) || "null";
                    }
                    v = partial.length === 0 ? "[]" : "[" + partial.join(",") + "]";
                    return v;
                }
                for (k in value) {
                    if (Object.prototype.hasOwnProperty.call(value, k)) {
                        v = str(k, value);
                        if (v) {
                            partial.push(quote(String(k)) + ":" + v);
                        }
                    }
                }
                v = partial.length === 0 ? "{}" : "{" + partial.join(",") + "}";
                return v;
        }
    }
    if (typeof JSON.stringify !== "function") {
        JSON.stringify = function (value) {
            return str("", { "": value });
        };
    }
    if (typeof JSON.parse !== "function") {
        JSON.parse = function (text) {
            return eval("(" + text + ")");
        };
    }
})();

var AEMCP = (function () {
    var pub = {};

    pub.ensurePermissions = function () {
        try {
            app.preferences.savePrefAsLong("Main Pref Section v2", "Pref_SCRIPTING_FILE_NETWORK_SECURITY", 1);
        } catch (e1) {}
        try {
            app.preferences.savePrefAsLong("Main Pref Section", "Pref_SCRIPTING_FILE_NETWORK_SECURITY", 1);
        } catch (e2) {}
        try {
            app.preferences.saveToDisk();
            app.preferences.reload();
        } catch (e3) {}
    };

    var PROP_ALIAS_MAP = {
        "transform": "ADBE Transform Group",
        "transformar": "ADBE Transform Group",
        "effects": "ADBE Effect Parade",
        "effect": "ADBE Effect Parade",
        "efectos": "ADBE Effect Parade",
        "masks": "ADBE Mask Parade",
        "mascaras": "ADBE Mask Parade",
        "máscaras": "ADBE Mask Parade",
        "text": "ADBE Text Properties",
        "texto": "ADBE Text Properties",
        "sourcetext": "ADBE Text Document",
        "source text": "ADBE Text Document",
        "texto de origen": "ADBE Text Document",
        "contents": "ADBE Root Vectors Group",
        "contenido": "ADBE Root Vectors Group",
        "audio": "ADBE Audio Group",
        "audiolevels": "ADBE Audio Levels",
        "audio levels": "ADBE Audio Levels",
        "niveles de audio": "ADBE Audio Levels",
        "anchorpoint": "ADBE Anchor Point",
        "anchor point": "ADBE Anchor Point",
        "punto de anclaje": "ADBE Anchor Point",
        "position": "ADBE Position",
        "posicion": "ADBE Position",
        "posición": "ADBE Position",
        "scale": "ADBE Scale",
        "escala": "ADBE Scale",
        "rotation": "ADBE Rotate Z",
        "rotacion": "ADBE Rotate Z",
        "rotación": "ADBE Rotate Z",
        "z rotation": "ADBE Rotate Z",
        "x rotation": "ADBE Rotate X",
        "rotacion x": "ADBE Rotate X",
        "rotación x": "ADBE Rotate X",
        "y rotation": "ADBE Rotate Y",
        "rotacion y": "ADBE Rotate Y",
        "rotación y": "ADBE Rotate Y",
        "orientation": "ADBE Orientation",
        "orientacion": "ADBE Orientation",
        "orientación": "ADBE Orientation",
        "opacity": "ADBE Opacity",
        "opacidad": "ADBE Opacity",
        "timeremap": "ADBE Time Remapping",
        "time remap": "ADBE Time Remapping",
        "time remapping": "ADBE Time Remapping",
        "remapeo de tiempo": "ADBE Time Remapping",
        "marker": "ADBE Marker",
        "markers": "ADBE Marker",
        "marcador": "ADBE Marker"
    };

    pub.findComp = function (compNameOrId) {
        if (!app.project) return null;
        if (compNameOrId !== undefined && compNameOrId !== null && compNameOrId !== "") {
            // Check by numeric ID first
            if (typeof compNameOrId === "number" || /^\d+$/.test(String(compNameOrId))) {
                var numId = parseInt(compNameOrId, 10);
                for (var i = 1; i <= app.project.numItems; i++) {
                    var itemById = app.project.item(i);
                    if (itemById instanceof CompItem && itemById.id === numId) {
                        return itemById;
                    }
                }
            }
            // Exact match by name
            var targetName = String(compNameOrId);
            for (var j = 1; j <= app.project.numItems; j++) {
                var it = app.project.item(j);
                if (it instanceof CompItem && it.name === targetName) {
                    return it;
                }
            }
            // Case-insensitive match
            var lowerTarget = targetName.toLowerCase();
            for (var k = 1; k <= app.project.numItems; k++) {
                var it2 = app.project.item(k);
                if (it2 instanceof CompItem && it2.name.toLowerCase() === lowerTarget) {
                    return it2;
                }
            }
        }
        // Fallback to activeItem
        if (app.project.activeItem && app.project.activeItem instanceof CompItem) {
            return app.project.activeItem;
        }
        // Fallback to first CompItem in project if unambiguous
        for (var m = 1; m <= app.project.numItems; m++) {
            var it3 = app.project.item(m);
            if (it3 instanceof CompItem) {
                return it3;
            }
        }
        return null;
    };

    pub.findLayer = function (comp, layerIndexOrName) {
        if (!comp || !(comp instanceof CompItem)) return null;
        if (typeof layerIndexOrName === "number" || /^\d+$/.test(String(layerIndexOrName))) {
            var idx = parseInt(layerIndexOrName, 10);
            if (idx >= 1 && idx <= comp.numLayers) {
                return comp.layer(idx);
            }
        }
        var nameStr = String(layerIndexOrName);
        try {
            var byName = comp.layer(nameStr);
            if (byName) return byName;
        } catch (e) {}
        var lower = nameStr.toLowerCase();
        for (var i = 1; i <= comp.numLayers; i++) {
            if (comp.layer(i).name.toLowerCase() === lower) {
                return comp.layer(i);
            }
        }
        return null;
    };

    pub.getOrCreateFolder = function (folderName, parentFolder) {
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof FolderItem && it.name === folderName) {
                if (!parentFolder || it.parentFolder === parentFolder) {
                    return it;
                }
            }
        }
        var f = app.project.items.addFolder(folderName);
        if (parentFolder && parentFolder instanceof FolderItem) {
            f.parentFolder = parentFolder;
        }
        return f;
    };

    pub.backupComp = function (comp, suffix) {
        if (!comp || !(comp instanceof CompItem)) return null;
        var backupFolder = pub.getOrCreateFolder("_MCP_SNAPSHOTS");
        var dup = comp.duplicate();
        var stamp = suffix || (new Date().getTime());
        dup.name = comp.name + "_SNAP_" + stamp;
        dup.parentFolder = backupFolder;
        return {
            id: dup.id,
            name: dup.name,
            folder: backupFolder.name
        };
    };

    pub.getLayerType = function (layer) {
        if (layer instanceof CameraLayer) return "CameraLayer";
        if (layer instanceof LightLayer) return "LightLayer";
        if (layer instanceof TextLayer) return "TextLayer";
        if (layer instanceof ShapeLayer) return "ShapeLayer";
        if (layer instanceof AVLayer) {
            if (layer.adjustmentLayer) return "AdjustmentLayer";
            if (layer.nullLayer) return "NullLayer";
            if (layer.source instanceof CompItem) return "PrecompLayer";
            if (layer.source instanceof FootageItem) {
                if (layer.source.mainSource instanceof SolidSource) return "SolidLayer";
                return "FootageLayer";
            }
            return "AVLayer";
        }
        return "Layer";
    };

    pub.safePropValue = function (prop, timeSec) {
        try {
            if (prop.propertyType !== PropertyType.PROPERTY) return null;
            if (prop.propertyValueType === PropertyValueType.NO_VALUE) return null;
            if (prop.propertyValueType === PropertyValueType.CUSTOM_VALUE) return "<CustomValue>";
            var v = (timeSec !== undefined && timeSec !== null) ? prop.valueAtTime(timeSec, false) : prop.value;
            if (v === null || v === undefined) return null;
            if (prop.propertyValueType === PropertyValueType.TEXT_DOCUMENT) {
                var td = {
                    text: v.text,
                    font: v.font,
                    fontSize: v.fontSize,
                    applyFill: v.applyFill,
                    applyStroke: v.applyStroke,
                    justification: String(v.justification)
                };
                try { if (v.applyFill) td.fillColor = v.fillColor; } catch (e1) {}
                try { if (v.applyStroke) td.strokeColor = v.strokeColor; } catch (e2) {}
                return td;
            }
            if (prop.propertyValueType === PropertyValueType.SHAPE) {
                return {
                    closed: v.closed,
                    numVertices: v.vertices ? v.vertices.length : 0
                };
            }
            if (v instanceof Array) {
                var cleanArr = [];
                for (var i = 0; i < v.length; i++) {
                    cleanArr.push(typeof v[i] === "number" ? Math.round(v[i] * 10000) / 10000 : v[i]);
                }
                return cleanArr;
            }
            if (typeof v === "number") {
                return Math.round(v * 10000) / 10000;
            }
            return v;
        } catch (err) {
            return null;
        }
    };

    pub.resolveProperty = function (layer, propPath) {
        if (!layer || !propPath) return null;
        var parts = [];
        if (propPath instanceof Array) {
            parts = propPath;
        } else {
            parts = String(propPath).split(".");
        }
        var current = layer;
        for (var i = 0; i < parts.length; i++) {
            var token = parts[i];
            if (token === "" || token === null || token === undefined) continue;
            var tokenStr = String(token);
            var lowerToken = tokenStr.toLowerCase();
            var aliasMatchName = PROP_ALIAS_MAP.hasOwnProperty(lowerToken) ? PROP_ALIAS_MAP[lowerToken] : null;
            var next = null;

            // 1. Try numeric index or direct matchName/name lookup
            try {
                if (/^\d+$/.test(tokenStr)) {
                    next = current.property(parseInt(tokenStr, 10));
                } else {
                    next = current.property(tokenStr);
                }
            } catch (e) {}

            // 2. Try universal multi-language matchName alias
            if (!next && aliasMatchName) {
                try {
                    next = current.property(aliasMatchName);
                } catch (e2) {}
            }

            // 3. If at Layer root and user gave a direct Transform/Text/Audio child (e.g. "Opacity", "Position", "Source Text")
            if (!next && i === 0) {
                var targetKey = aliasMatchName || tokenStr;
                var rootGroups = ["ADBE Transform Group", "ADBE Text Properties", "ADBE Audio Group", "ADBE Effect Parade"];
                for (var g = 0; g < rootGroups.length; g++) {
                    try {
                        var grp = current.property(rootGroups[g]);
                        if (grp) {
                            next = grp.property(targetKey) || grp.property(tokenStr);
                            if (next) break;
                        }
                    } catch (e3) {}
                }
            }

            // 4. Case-insensitive scan of child properties if still not found
            if (!next && current.numProperties) {
                for (var c = 1; c <= current.numProperties; c++) {
                    try {
                        var child = current.property(c);
                        if (
                            String(child.name).toLowerCase() === lowerToken ||
                            String(child.matchName).toLowerCase() === lowerToken
                        ) {
                            next = child;
                            break;
                        }
                    } catch (e4) {}
                }
            }

            if (!next) return null;
            current = next;
        }
        return current;
    };

    pub.serializePropertyTree = function (propGroup, currentDepth, maxDepth, includeKeyframes) {
        if (currentDepth > maxDepth) return null;
        var out = {
            name: propGroup.name,
            matchName: propGroup.matchName,
            propertyIndex: propGroup.propertyIndex
        };
        if (propGroup.propertyType === PropertyType.PROPERTY) {
            out.type = "Property";
            out.value = pub.safePropValue(propGroup);
            out.numKeys = propGroup.numKeys || 0;
            try {
                if (propGroup.expressionEnabled || (propGroup.expression && propGroup.expression !== "")) {
                    out.expression = propGroup.expression;
                    out.expressionEnabled = propGroup.expressionEnabled;
                    out.expressionError = propGroup.expressionError || "";
                }
            } catch (e) {}
            if (includeKeyframes && propGroup.numKeys > 0) {
                var keys = [];
                var limit = Math.min(propGroup.numKeys, 100);
                for (var k = 1; k <= limit; k++) {
                    keys.push({
                        index: k,
                        time: Math.round(propGroup.keyTime(k) * 10000) / 10000,
                        value: pub.safePropValue(propGroup, propGroup.keyTime(k))
                    });
                }
                out.keyframes = keys;
            }
        } else {
            out.type = "Group";
            out.numProperties = propGroup.numProperties || 0;
            if (currentDepth < maxDepth && propGroup.numProperties > 0) {
                out.children = [];
                for (var i = 1; i <= propGroup.numProperties; i++) {
                    try {
                        var child = propGroup.property(i);
                        // Skip hidden/modified-only noise unless it's an effect or modified
                        var childData = pub.serializePropertyTree(child, currentDepth + 1, maxDepth, includeKeyframes);
                        if (childData) out.children.push(childData);
                    } catch (eChild) {}
                }
            }
        }
        return out;
    };

    pub.serializeLayer = function (layer, opts) {
        opts = opts || {};
        var info = {
            index: layer.index,
            name: layer.name,
            type: pub.getLayerType(layer),
            enabled: layer.enabled,
            solo: layer.solo,
            shy: layer.shy,
            locked: layer.locked,
            inPoint: Math.round(layer.inPoint * 10000) / 10000,
            outPoint: Math.round(layer.outPoint * 10000) / 10000,
            startTime: Math.round(layer.startTime * 10000) / 10000,
            stretch: layer.stretch,
            parentIndex: layer.parent ? layer.parent.index : null,
            parentName: layer.parent ? layer.parent.name : null
        };
        try {
            info.threeDLayer = Boolean(layer.threeDLayer);
            info.blendingMode = String(layer.blendingMode);
            if (layer.source) {
                info.sourceName = layer.source.name;
                info.sourceId = layer.source.id;
            }
        } catch (e) {}

        if (opts.includeTransform !== false) {
            try {
                var tr = layer.property("ADBE Transform Group");
                if (tr) {
                    info.transform = {
                        anchorPoint: pub.safePropValue(tr.property("ADBE Anchor Point")),
                        position: pub.safePropValue(tr.property("ADBE Position")),
                        scale: pub.safePropValue(tr.property("ADBE Scale")),
                        rotation: pub.safePropValue(tr.property("ADBE Rotate Z")),
                        opacity: pub.safePropValue(tr.property("ADBE Opacity"))
                    };
                }
            } catch (eTr) {}
        }

        if (opts.includeEffects !== false) {
            try {
                var fxParade = layer.property("ADBE Effect Parade");
                if (fxParade && fxParade.numProperties > 0) {
                    info.effects = [];
                    for (var f = 1; f <= fxParade.numProperties; f++) {
                        var fx = fxParade.property(f);
                        var fxObj = {
                            index: f,
                            name: fx.name,
                            matchName: fx.matchName,
                            enabled: fx.enabled
                        };
                        if (opts.includeEffectParams) {
                            fxObj.params = [];
                            for (var p = 1; p <= Math.min(fx.numProperties, 40); p++) {
                                var pr = fx.property(p);
                                if (pr.propertyType === PropertyType.PROPERTY) {
                                    var pVal = pub.safePropValue(pr);
                                    if (pVal !== null) {
                                        fxObj.params.push({
                                            index: p,
                                            name: pr.name,
                                            matchName: pr.matchName,
                                            value: pVal,
                                            numKeys: pr.numKeys || 0
                                        });
                                    }
                                }
                            }
                        }
                        info.effects.push(fxObj);
                    }
                }
            } catch (eFx) {}
        }

        if (layer instanceof TextLayer) {
            try {
                var srcText = layer.property("ADBE Text Properties").property("ADBE Text Document");
                info.textDocument = pub.safePropValue(srcText);
            } catch (eTxt) {}
        }

        return info;
    };

    return pub;
})();
