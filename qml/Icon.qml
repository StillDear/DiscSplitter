import QtQuick

// Geometry-only icons: independent of installed font glyphs.
Canvas {
    property string kind: "disc"
    property color ink: Theme.accent
    implicitWidth: 24
    implicitHeight: 24
    onKindChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        ctx.save()
        ctx.scale(width / 24, height / 24)
        ctx.strokeStyle = ink
        ctx.lineWidth = 1.8
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.beginPath()
        if (kind === "disc") {
            ctx.arc(12, 12, 9, 0, Math.PI * 2)
            ctx.moveTo(14.5, 12)
            ctx.arc(12, 12, 2.5, 0, Math.PI * 2)
            ctx.moveTo(12, 6)
            ctx.arc(12, 12, 6, -Math.PI / 2, 0)
        } else if (kind === "film") {
            // a strip of film: frame with a band of perforations down each side
            ctx.rect(3.5, 4.5, 17, 15)
            ctx.moveTo(7.5, 4.5); ctx.lineTo(7.5, 19.5)
            ctx.moveTo(16.5, 4.5); ctx.lineTo(16.5, 19.5)
            ctx.moveTo(3.5, 12); ctx.lineTo(7.5, 12)
            ctx.moveTo(16.5, 12); ctx.lineTo(20.5, 12)
        } else if (kind === "refresh") {
            ctx.arc(12, 12, 8, Math.PI, Math.PI * 1.285, true)
            ctx.moveTo(4, 4)
            ctx.lineTo(4, 8)
            ctx.lineTo(8, 8)
        } else if (kind === "more") {
            // three dots, filled below
            for (let i = 0; i < 3; i++) { ctx.moveTo(7.6 + i * 6, 12); ctx.arc(6 + i * 6, 12, 1.6, 0, Math.PI * 2) }
            ctx.fillStyle = ink
            ctx.fill()
        } else if (kind === "scissors") {
            ctx.moveTo(9.5, 6.5)
            ctx.arc(6.5, 6.5, 3, 0, Math.PI * 2)
            ctx.moveTo(9.5, 17.5)
            ctx.arc(6.5, 17.5, 3, 0, Math.PI * 2)
            ctx.moveTo(8.8, 8.6)
            ctx.lineTo(20, 17)
            ctx.moveTo(8.8, 15.4)
            ctx.lineTo(20, 7)
        } else if (kind === "check") {
            ctx.lineWidth = 2.6
            ctx.moveTo(5, 12)
            ctx.lineTo(10, 17)
            ctx.lineTo(19, 7)
        } else if (kind === "gear") {
            // Toothed outline: 8 teeth with slanted flanks, plus the centre hole.
            const teeth = 8, outer = 10, inner = 7.4, step = Math.PI * 2 / teeth
            const pt = function(r, a) { return [12 + r * Math.cos(a), 12 + r * Math.sin(a)] }
            for (let i = 0; i < teeth; i++) {
                const a = i * step - Math.PI / 2
                const p = [pt(inner, a - step * 0.36), pt(outer, a - step * 0.2), pt(outer, a + step * 0.2), pt(inner, a + step * 0.36)]
                if (i === 0) ctx.moveTo(p[0][0], p[0][1]); else ctx.lineTo(p[0][0], p[0][1])
                for (let k = 1; k < 4; k++) ctx.lineTo(p[k][0], p[k][1])
            }
            ctx.closePath()
            ctx.moveTo(15.2, 12)
            ctx.arc(12, 12, 3.2, 0, Math.PI * 2)
        } else if (kind === "help") {
            ctx.arc(12, 12, 9, 0, Math.PI * 2)
            ctx.moveTo(9.5, 9.5)
            ctx.bezierCurveTo(9.5, 6.5, 14.5, 6.5, 14.5, 9.5)
            ctx.bezierCurveTo(14.5, 11.5, 12, 11.5, 12, 13.5)
            ctx.moveTo(12, 16.8)
            ctx.lineTo(12, 17)
        } else if (kind === "down") {
            ctx.lineWidth = 2
            ctx.moveTo(6, 9)
            ctx.lineTo(12, 15)
            ctx.lineTo(18, 9)
        } else if (kind === "back") {
            ctx.lineWidth = 2.2
            ctx.moveTo(15, 5)
            ctx.lineTo(8, 12)
            ctx.lineTo(15, 19)
        } else if (kind === "folder") {
            ctx.moveTo(3, 6)
            ctx.lineTo(9, 6)
            ctx.lineTo(11, 8)
            ctx.lineTo(21, 8)
            ctx.lineTo(21, 19)
            ctx.lineTo(3, 19)
            ctx.closePath()
        } else if (kind === "alert") {
            ctx.moveTo(12, 5)
            ctx.lineTo(12, 14)
            ctx.moveTo(12, 18)
            ctx.lineTo(12, 18.2)
        } else if (kind === "expand") {
            ctx.moveTo(14, 4.5); ctx.lineTo(19.5, 4.5); ctx.lineTo(19.5, 10)
            ctx.moveTo(19.5, 4.5); ctx.lineTo(13.5, 10.5)
            ctx.moveTo(10, 19.5); ctx.lineTo(4.5, 19.5); ctx.lineTo(4.5, 14)
            ctx.moveTo(4.5, 19.5); ctx.lineTo(10.5, 13.5)
        } else if (kind === "shrink") {
            ctx.moveTo(13.5, 5); ctx.lineTo(13.5, 10.5); ctx.lineTo(19, 10.5)
            ctx.moveTo(13.5, 10.5); ctx.lineTo(19.5, 4.5)
            ctx.moveTo(10.5, 19); ctx.lineTo(10.5, 13.5); ctx.lineTo(5, 13.5)
            ctx.moveTo(10.5, 13.5); ctx.lineTo(4.5, 19.5)
        } else if (kind === "wave") {
            ctx.moveTo(4, 10); ctx.lineTo(4, 14)
            ctx.moveTo(8, 7); ctx.lineTo(8, 17)
            ctx.moveTo(12, 4); ctx.lineTo(12, 20)
            ctx.moveTo(16, 8); ctx.lineTo(16, 16)
            ctx.moveTo(20, 10.5); ctx.lineTo(20, 13.5)
        } else if (kind === "info") {
            ctx.arc(12, 12, 8.5, 0, Math.PI * 2)
            ctx.moveTo(12, 11)
            ctx.lineTo(12, 16.5)
            ctx.moveTo(12, 7.6)
            ctx.lineTo(12, 7.8)
        } else if (kind === "play") {
            ctx.moveTo(8, 5.5)
            ctx.lineTo(18.5, 12)
            ctx.lineTo(8, 18.5)
            ctx.closePath()
        } else if (kind === "pause") {
            ctx.rect(7, 5.5, 3.2, 13)
            ctx.rect(13.8, 5.5, 3.2, 13)
        } else if (kind === "prev") {
            ctx.moveTo(18, 6)
            ctx.lineTo(9.5, 12)
            ctx.lineTo(18, 18)
            ctx.closePath()
            ctx.rect(6, 6, 1.6, 12)
        } else if (kind === "next") {
            ctx.moveTo(6, 6)
            ctx.lineTo(14.5, 12)
            ctx.lineTo(6, 18)
            ctx.closePath()
            ctx.rect(16.4, 6, 1.6, 12)
        } else if (kind === "close") {
            ctx.moveTo(6.5, 6.5)
            ctx.lineTo(17.5, 17.5)
            ctx.moveTo(17.5, 6.5)
            ctx.lineTo(6.5, 17.5)
        } else if (kind === "volume") {
            ctx.moveTo(4, 9.5)
            ctx.lineTo(7.5, 9.5)
            ctx.lineTo(12, 5.5)
            ctx.lineTo(12, 18.5)
            ctx.lineTo(7.5, 14.5)
            ctx.lineTo(4, 14.5)
            ctx.closePath()
            ctx.moveTo(15.5, 9)
            ctx.quadraticCurveTo(17.5, 12, 15.5, 15)
            ctx.moveTo(18, 6.5)
            ctx.quadraticCurveTo(22, 12, 18, 17.5)
        }
        if (kind === "play" || kind === "pause" || kind === "prev" || kind === "next") {
            ctx.fillStyle = ink
            ctx.fill()
        }
        ctx.stroke()
        ctx.restore()
    }
}
