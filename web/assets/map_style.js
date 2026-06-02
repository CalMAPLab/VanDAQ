// dash-leaflet styling functions for the VanDAQ map.
//
// Auto-loaded by Dash from assets/. Referenced from Python via
// dash_extensions.javascript.Namespace as dashExtensions.vandaqMap.
//
// Canvas renderer (L.canvas) supports tens of thousands of circleMarkers
// without the default SVG renderer choking.

window.dashExtensions = Object.assign({}, window.dashExtensions, {
    vandaqMap: {
        _canvasRenderer: null,
        getCanvasRenderer: function() {
            if (!this._canvasRenderer) {
                this._canvasRenderer = L.canvas({padding: 0.5});
            }
            return this._canvasRenderer;
        },

        lerpHex: function(hexA, hexB, t) {
            const a = parseInt(hexA.slice(1), 16);
            const b = parseInt(hexB.slice(1), 16);
            const ar = (a >> 16) & 0xff, ag = (a >> 8) & 0xff, ab = a & 0xff;
            const br = (b >> 16) & 0xff, bg = (b >> 8) & 0xff, bb = b & 0xff;
            const r = Math.round(ar + (br - ar) * t);
            const g = Math.round(ag + (bg - ag) * t);
            const bl = Math.round(ab + (bb - ab) * t);
            return "#" + ((1 << 24) | (r << 16) | (g << 8) | bl).toString(16).slice(1);
        },

        colorAt: function(colorscale, t) {
            if (t <= 0) return colorscale[0];
            if (t >= 1) return colorscale[colorscale.length - 1];
            const scaled = t * (colorscale.length - 1);
            const i = Math.floor(scaled);
            const frac = scaled - i;
            return this.lerpHex(colorscale[i], colorscale[i + 1], frac);
        },

        point_to_layer: function(feature, latlng, context) {
            const ns = window.dashExtensions.vandaqMap;
            const {min, max, colorscale, circleOptions} = context.hideout;
            const v = feature.properties.value;
            let t = 0.5;
            if (typeof v === "number" && isFinite(v) && max > min) {
                t = (v - min) / (max - min);
                if (t < 0) t = 0;
                if (t > 1) t = 1;
            }
            const fillColor = ns.colorAt(colorscale, t);
            const opts = Object.assign({}, circleOptions || {}, {
                renderer: ns.getCanvasRenderer(),
                fillColor: fillColor,
                color: fillColor,
            });
            return L.circleMarker(latlng, opts);
        },

        on_each_feature: function(feature, layer, context) {
            const p = feature.properties || {};
            if (p.tooltip) {
                layer.bindTooltip(p.tooltip, {sticky: true});
            }
        },
    }
});
