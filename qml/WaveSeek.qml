import QtQuick
// Seek bar that can draw the clip's loudness outline: played part in accent, the rest muted.
Item {
    id: seek
    property var peaks: []
    property bool showWave: true
    property real position: 0          // ms
    property real duration: 0          // ms
    property bool interactive: true
    property color played: Theme.accent
    property color rest: Theme.line2
    signal moved(real ms)

    property bool dragging: false
    property real dragFraction: 0
    readonly property bool hasWave: showWave && peaks !== undefined && peaks !== null && peaks.length > 1
    readonly property real fraction: duration > 0 ? Math.min(1, Math.max(0, dragging ? dragFraction : position / duration)) : 0
    readonly property real shownMs: dragging ? dragFraction * duration : position
    implicitHeight: 18

    function paintWave(canvas, ink) {
        const ctx = canvas.getContext("2d")
        ctx.reset()
        const list = seek.peaks, n = list ? list.length : 0
        if (n < 2 || canvas.width <= 0) return
        const w = canvas.width, h = canvas.height, mid = h / 2
        const step = 3, bars = Math.max(1, Math.floor(w / step))
        ctx.fillStyle = ink
        for (let i = 0; i < bars; i++) {
            const a = Math.floor(i * n / bars), b = Math.max(a + 1, Math.floor((i + 1) * n / bars))
            let m = 0
            for (let j = a; j < b && j < n; j++) if (list[j] > m) m = list[j]
            const bh = Math.max(1.5, Math.sqrt(m) * (h - 2))
            ctx.fillRect(i * step, mid - bh / 2, 2, bh)
        }
    }

    // Plain track when there is no outline (or it is switched off)
    Rectangle {
        visible: !seek.hasWave
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width; height: 4; radius: 2; color: seek.rest
        Rectangle { width: seek.fraction * parent.width; height: parent.height; radius: 2; color: seek.played }
    }
    Canvas {
        id: restWave
        anchors.fill: parent; visible: seek.hasWave
        onPaint: seek.paintWave(restWave, seek.rest)
    }
    Item {
        visible: seek.hasWave
        width: seek.fraction * seek.width; height: seek.height; clip: true
        Canvas {
            id: playedWave
            width: seek.width; height: seek.height
            onPaint: seek.paintWave(playedWave, seek.played)
        }
    }
    function repaint() { restWave.requestPaint(); playedWave.requestPaint() }
    onPeaksChanged: repaint()
    onShowWaveChanged: repaint()
    onWidthChanged: repaint()
    onHeightChanged: repaint()
    onPlayedChanged: repaint()
    onRestChanged: repaint()

    // Playhead
    Rectangle {
        visible: seek.duration > 0
        x: seek.fraction * (seek.width - width); anchors.verticalCenter: parent.verticalCenter
        width: seek.hasWave ? 2 : 12; height: seek.hasWave ? seek.height : 12; radius: seek.hasWave ? 1 : 6
        color: seek.played
        scale: !seek.hasWave && (area.containsMouse || seek.dragging) ? 1.15 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
    }
    MouseArea {
        id: area
        anchors.fill: parent; anchors.topMargin: -4; anchors.bottomMargin: -4
        enabled: seek.interactive && seek.duration > 0; hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        function at(x) { return Math.min(1, Math.max(0, x / Math.max(1, seek.width))) }
        onPressed: function(mouse) { seek.dragFraction = at(mouse.x); seek.dragging = true }
        onPositionChanged: function(mouse) { if (pressed) seek.dragFraction = at(mouse.x) }
        onReleased: { seek.moved(seek.dragFraction * seek.duration); seek.dragging = false }
        onCanceled: seek.dragging = false
    }
}
