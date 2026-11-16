import QtQuick

// The play of colour on a disc's surface: a thin iridescent edge laid over a rounded shape, and a band of light
// that sweeps across it once (sweep()), as when a disc is tilted under a lamp. Drawn with Canvas, so it needs no
// shaders. Put it over the shape (anchors.fill) with the shape's radius; it never takes clicks.
Canvas {
    id: sheen
    property real radius: 8
    property real lineWidth: 1.5
    property bool on: true
    property real phase: -1                 // where the band of light is, 0..1 across; outside: no band
    readonly property real strength: Theme.light ? 1 : 0.85
    // Pastel spectrum, as a disc reflects it
    readonly property var spectrum: ["#7CD3FF", "#9B8CFF", "#F59AD0", "#FFD58A", "#8DEBB4", "#7CD3FF"]

    opacity: on ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.normal } }

    function sweep() {
        if (!Theme.animate || width <= 0) return
        band.restart()
    }

    NumberAnimation {
        id: band; target: sheen; property: "phase"
        from: -0.35; to: 1.35; duration: 900; easing.type: Easing.InOutSine
        onStopped: sheen.phase = -1
    }
    onPhaseChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onRadiusChanged: requestPaint()
    onStrengthChanged: requestPaint()

    function shape(ctx, inset) {
        const w = width - inset * 2, h = height - inset * 2, r = Math.max(0, Math.min(radius - inset, w / 2, h / 2))
        ctx.beginPath()
        ctx.moveTo(inset + r, inset)
        ctx.arcTo(inset + w, inset, inset + w, inset + h, r)
        ctx.arcTo(inset + w, inset + h, inset, inset + h, r)
        ctx.arcTo(inset, inset + h, inset, inset, r)
        ctx.arcTo(inset, inset, inset + w, inset, r)
        ctx.closePath()
    }

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        if (width <= 0 || height <= 0) return
        // The iridescent edge
        const edge = ctx.createLinearGradient(0, 0, width, height)
        for (let i = 0; i < spectrum.length; i++) edge.addColorStop(i / (spectrum.length - 1), spectrum[i])
        ctx.globalAlpha = strength
        ctx.lineWidth = lineWidth
        ctx.strokeStyle = edge
        shape(ctx, lineWidth / 2)
        ctx.stroke()
        // The band of light, slanted, inside the shape only
        if (phase > -0.35 && phase < 1.35) {
            ctx.save()
            shape(ctx, 0)
            ctx.clip()
            const x = phase * width, half = Math.max(24, width * 0.18)
            const light = ctx.createLinearGradient(x - half, 0, x + half, height * 0.4)
            light.addColorStop(0, Qt.rgba(1, 1, 1, 0))
            light.addColorStop(0.5, Qt.rgba(1, 1, 1, Theme.light ? 0.55 : 0.32))
            light.addColorStop(1, Qt.rgba(1, 1, 1, 0))
            ctx.globalAlpha = 1
            ctx.fillStyle = light
            ctx.fillRect(0, 0, width, height)
            ctx.restore()
        }
    }
}
