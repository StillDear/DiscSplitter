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
    // Hairlines and frames; with a blue cast in disc mode (below)
    readonly property color line: discTint(light ? "#DFE2E7" : "#232830", light ? 0.30 : 0.38)
    readonly property color line2: discTint(light ? "#CDD2DA" : "#2F3541", light ? 0.34 : 0.42)
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
    readonly property color chosenAccent: backend.config.accent === "system" ? (backend.view.systemAccent || "#60CDFF") : (backend.config.accent || "#F2A33A")
    // A copy of the disc (M2TS) has the blue of a Blu-ray (not in the settings, where colours are being chosen):
    // laid over frames and selected backgrounds, keeping the accent ("tint", the default), or as the accent itself.
    readonly property bool discMode: backend.disc.view.outputFormat === "m2ts" && backend.view.page !== "settings"
    readonly property bool discReplace: discMode && backend.config.disc_colors === "replace"
    readonly property bool discTinted: discMode && !discReplace
    readonly property color discBlue: "#3D74E0"
    readonly property color accent: discReplace ? discBlue : chosenAccent
    function discTint(c, amount) { return discTinted ? Qt.tint(c, Qt.rgba(discBlue.r, discBlue.g, discBlue.b, amount)) : c }
    readonly property real accentLuma: 0.2126 * accent.r + 0.7152 * accent.g + 0.0722 * accent.b
    // Text drawn on an accent fill: dark on bright accents, white on deep ones (e.g. Windows blue).
    readonly property color accentInk: accentLuma > 0.45 ? "#14100A" : "#FFFFFF"
    // Accent used as text on the page background, kept readable in both themes.
    readonly property color accentText: light ? (accentLuma > 0.35 ? Qt.darker(accent, 1.75) : accent)
                                              : (accentLuma < 0.45 ? Qt.lighter(accent, 1.5) : accent)
    // "transparent" is transparent *black*: a colour animated to or from it passes through grey (a dark
    // smear on a light hover). Fade to the same colour with no alpha instead.
    function clear(c) { return Qt.rgba(c.r, c.g, c.b, 0) }
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
    // Selected backgrounds: the accent, faint; tinted disc mode uses the disc's blue instead
    readonly property color accentSoft: discTinted ? discTint(panel, light ? 0.12 : 0.14)
                                                   : Qt.tint(panel, Qt.rgba(accent.r, accent.g, accent.b, light ? 0.14 : 0.12))
    readonly property color accentSoft2: discTinted ? discTint(panel, light ? 0.22 : 0.24)
                                                    : Qt.tint(panel, Qt.rgba(accent.r, accent.g, accent.b, light ? 0.26 : 0.22))
    // Type. Chinese falls back from Segoe UI to Microsoft YaHei UI, whose own Latin letters run wider
    // and would crowd the chips and cards, so the family stays Segoe UI in both languages.
    readonly property string ui: "Segoe UI"
    // Heading weight: YaHei has no semibold, so a DemiBold Chinese title would come out regular.
    readonly property int strong: backend.config.language === "zh" ? Font.Bold : Font.DemiBold
    readonly property string mono: "Consolas"       // paths, file names, logs
    readonly property string num: ui                // times, counts and sizes, with tabular digits so columns line up
    readonly property var tabular: ({ "tnum": 1 })
    // Type scale: page title, dialog title, section heading, list item, body, small, caption
    readonly property int display: px(24)
    readonly property int title: px(18)
    readonly property int heading: px(15)
    readonly property int item: px(14)
    readonly property int body: px(13)
    readonly property int small: px(12)
    readonly property int caption: px(11)
}
