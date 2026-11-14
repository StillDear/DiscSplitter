pragma Singleton
import QtQuick
QtObject {
    readonly property bool light: backend.config.theme === "light" || (backend.config.theme === "system" && Qt.styleHints.colorScheme === Qt.Light)
    // Surfaces
    readonly property color bg: light ? "#EEF0F3" : "#0C0E12"
    readonly property color panel: light ? "#FFFFFF" : "#15181E"
    readonly property color raised: light ? "#F6F7F9" : "#1C2028"
    readonly property color deep: light ? "#F6F7F9" : "#0C0E12"
    readonly property color field: light ? "#FFFFFF" : "#0C0E12"
    readonly property color segOn: light ? "#FFFFFF" : "#2B313B"
    readonly property color chip: light ? "#ECEEF2" : "#232830"
    // Lines
    readonly property color line: light ? "#DFE2E7" : "#232830"
    readonly property color line2: light ? "#CDD2DA" : "#2F3541"
    // Text
    readonly property color text: light ? "#15181D" : "#E9EBEE"
    readonly property color sub: light ? "#3A404B" : "#C9CED6"
    readonly property color muted: light ? "#596170" : "#9BA3AE"
    readonly property color faint: light ? "#6B7380" : "#7D8590"
    // Status
    readonly property color good: light ? "#0B8A7D" : "#4FD1C5"
    readonly property color goodText: light ? "#075E56" : "#7FE3D8"
    readonly property color goodBg: light ? "#DDF3F0" : "#12302D"
    readonly property color danger: light ? "#B73530" : "#FFA59E"
    readonly property color dangerLine: light ? "#D9827E" : "#C9605A"
    readonly property color dangerBg: light ? "#FBE3E0" : "#3A2427"
    readonly property color pendingBg: light ? "#FBE3E0" : "#3A2427"   // e.g. chapters still without a title
    readonly property color pendingText: light ? "#A3322D" : "#FFB1AA"
    // Accent
    readonly property color accent: backend.config.accent === "system" ? (backend.view.systemAccent || "#60CDFF") : (backend.config.accent || "#F2A33A")
    readonly property real accentLuma: 0.2126 * accent.r + 0.7152 * accent.g + 0.0722 * accent.b
    // Text drawn on an accent fill: dark on bright accents, white on deep ones (e.g. Windows blue).
    readonly property color accentInk: accentLuma > 0.45 ? "#14100A" : "#FFFFFF"
    // Accent used as text on the page background, kept readable in both themes.
    readonly property color accentText: light ? (accentLuma > 0.35 ? Qt.darker(accent, 1.75) : accent)
                                              : (accentLuma < 0.45 ? Qt.lighter(accent, 1.5) : accent)
    // Motion
    readonly property bool animate: backend.config.motion !== "reduced"
    readonly property int fast: animate ? 120 : 0
    readonly property int normal: animate ? 200 : 0
    readonly property int slow: animate ? 340 : 0
    // Density
    readonly property bool compact: backend.config.density === "compact"
    // Text size: every font size goes through px(); rows grow with larger text.
    readonly property real fontScale: Number(backend.config.font_scale) || 1
    function px(size) { return Math.round(size * fontScale) }
    readonly property int rowHeight: Math.round((compact ? 36 : 44) * Math.max(1, fontScale))
    readonly property color accentSoft: Qt.tint(panel, Qt.rgba(accent.r, accent.g, accent.b, light ? 0.14 : 0.12))
    readonly property color accentSoft2: Qt.tint(panel, Qt.rgba(accent.r, accent.g, accent.b, light ? 0.26 : 0.22))
    // Type
    readonly property string ui: "Segoe UI"
    readonly property string mono: "Consolas"
}
