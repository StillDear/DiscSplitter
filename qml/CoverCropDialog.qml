import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: editor
    required property var win
    property var artwork: ({ url: "", width: 1, height: 1 })
    readonly property int cropWidth: artwork.width - leftTrim.value - rightTrim.value
    readonly property int cropHeight: artwork.height - topTrim.value - bottomTrim.value
    readonly property bool changedCrop: leftTrim.value + rightTrim.value + topTrim.value + bottomTrim.value > 0
    readonly property bool suggested: artwork.left > 0 || artwork.right > 0 || artwork.top > 0 || artwork.bottom > 0
    // Fixed (not themed) backdrop, so white or black borders stand out against it
    readonly property string backdrop: backend.config.crop_backdrop || "dark"

    parent: win.contentItem
    anchors.centerIn: parent
    width: Math.min(1100, parent.width - 48)
    height: Math.min(780, parent.height - 48)
    padding: 20
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    background: Rectangle { color: Theme.panel; border.color: Theme.line2; radius: 14 }

    function setMargins(left, right, top, bottom) {
        leftTrim.value = left
        rightTrim.value = right
        topTrim.value = top
        bottomTrim.value = bottom
    }

    function showCover() {
        const info = backend.metadata.coverCropInfo()
        if (!info.url) return
        artwork = info
        setMargins(info.left, info.right, info.top, info.bottom)
        mag = 1
        open()
    }

    // ---- zoom shared by both previews
    property real mag: 1
    property var stages: []
    property bool following: false
    readonly property real maxMag: stages.length ? Math.max(1, 8 / stages[0].fit) : 8   // up to 800% of the real pixels
    readonly property real pixelScale: stages.length ? stages[0].zoom : 1

    function setMag(value, stage, px, py) {
        value = Math.max(1, Math.min(maxMag, value))
        const anchor = stage || stages[0]
        if (!anchor) { mag = value; return }
        const ax = px === undefined ? anchor.width / 2 : px, ay = py === undefined ? anchor.height / 2 : py
        const pixel = anchor.pixelAt(ax, ay)
        mag = value
        anchor.showPixel(pixel, ax, ay)
        follow(anchor)
    }
    function zoomBy(factor, stage, px, py) { setMag(mag * factor, stage, px, py) }
    // keep the other preview centred on the same image pixel
    function follow(source) {
        if (following || !visible) return
        following = true
        const pixel = source.pixelAt(source.width / 2, source.height / 2)
        for (const s of stages)
            if (s !== source) s.showPixel(pixel, s.width / 2, s.height / 2)
        following = false
    }

    contentItem: ColumnLayout {
        spacing: 12
        Copy { text: editor.win.tr("cropCover"); font.pixelSize: Theme.px(20); font.bold: true }
        Copy {
            Layout.fillWidth: true
            text: editor.win.tr(editor.suggested ? "cropSuggested" : "cropManual")
            color: Theme.muted
        }

        // Zoom: 1 = fit. Both stages share the level and follow each other's position,
        // so an edge can be checked in the original and the preview side by side.
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            Copy { text: editor.win.tr("cropZoomHint"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; elide: Text.ElideRight }
            Copy { text: editor.win.tr("cropBackdrop"); color: Theme.muted; font.pixelSize: Theme.px(12) }
            Segmented {
                options: [{ key: "dark", label: editor.win.tr("cropBackdropDark") },
                          { key: "light", label: editor.win.tr("cropBackdropLight") },
                          { key: "checker", label: editor.win.tr("cropBackdropChecker") }]
                current: editor.backdrop
                onPicked: function(key) { backend.setPreference("crop_backdrop", key) }
                HoverHandler { id: backdropHover }
                ToolTip.visible: backdropHover.hovered; ToolTip.delay: 400; ToolTip.text: editor.win.tr("cropBackdropHint")
            }
            Item { Layout.preferredWidth: 10 }
            ActionButton { text: "−"; implicitHeight: 28; implicitWidth: 34; enabled: editor.mag > 1; onClicked: editor.zoomBy(1 / 1.5) }
            Copy {
                text: Math.round(editor.pixelScale * 100) + "%"; font.family: Theme.mono; font.pixelSize: Theme.px(12)
                horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 52
            }
            ActionButton { text: "+"; implicitHeight: 28; implicitWidth: 34; enabled: editor.mag < editor.maxMag; onClicked: editor.zoomBy(1.5) }
            ActionButton { text: editor.win.tr("cropFit"); implicitHeight: 28; selected: editor.mag === 1; onClicked: editor.setMag(1) }
            ActionButton { text: "100%"; implicitHeight: 28; onClicked: editor.setMag(editor.stages.length ? 1 / editor.stages[0].fit : 1) }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
            Repeater {
                model: [false, true]
                ColumnLayout {
                    id: preview
                    required property bool modelData
                    readonly property int imageWidth: modelData ? editor.cropWidth : editor.artwork.width
                    readonly property int imageHeight: modelData ? editor.cropHeight : editor.artwork.height
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1
                    Copy { text: editor.win.tr(preview.modelData ? "cropPreview" : "cropOriginal"); font.weight: Font.DemiBold }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        radius: 8; border.color: Theme.line
                        color: editor.backdrop === "light" ? "#F4F4F4" : editor.backdrop === "checker" ? "#FFFFFF" : "#2B2B2B"
                        Canvas {
                            id: checker
                            anchors.fill: parent; anchors.margins: 1
                            visible: editor.backdrop === "checker"
                            onWidthChanged: requestPaint()
                            onHeightChanged: requestPaint()
                            onVisibleChanged: if (visible) requestPaint()
                            onPaint: {
                                const ctx = getContext("2d"), cell = 10
                                ctx.clearRect(0, 0, width, height)
                                ctx.fillStyle = "#CFCFCF"
                                for (let y = 0; y < height; y += cell)
                                    for (let x = (y / cell) % 2 ? cell : 0; x < width; x += 2 * cell)
                                        ctx.fillRect(x, y, cell, cell)
                            }
                        }
                        Flickable {
                            id: stage
                            anchors.fill: parent; anchors.margins: 1; clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            interactive: editor.mag > 1
                            // offset of this stage's first visible image pixel in the original image
                            readonly property real offsetX: preview.modelData ? leftTrim.value : 0
                            readonly property real offsetY: preview.modelData ? topTrim.value : 0
                            readonly property real fit: Math.max(0.0001, Math.min((width - 16) / Math.max(1, preview.imageWidth),
                                                                                   (height - 16) / Math.max(1, preview.imageHeight)))
                            readonly property real zoom: fit * editor.mag
                            contentWidth: Math.max(width, preview.imageWidth * zoom + 16)
                            contentHeight: Math.max(height, preview.imageHeight * zoom + 16)
                            Component.onCompleted: editor.stages = editor.stages.concat([stage])
                            Component.onDestruction: editor.stages = editor.stages.filter(s => s !== stage)
                            onContentXChanged: editor.follow(stage)
                            onContentYChanged: editor.follow(stage)

                            // image pixel under a point of the stage (view coordinates)
                            function pixelAt(px, py) {
                                return Qt.point((contentX + px - frame.x) / zoom + offsetX, (contentY + py - frame.y) / zoom + offsetY)
                            }
                            // scroll so that an image pixel sits under a point of the stage
                            function showPixel(pixel, px, py) {
                                contentX = Math.max(0, Math.min(contentWidth - width, (pixel.x - offsetX) * zoom + frame.x - px))
                                contentY = Math.max(0, Math.min(contentHeight - height, (pixel.y - offsetY) * zoom + frame.y - py))
                            }

                            Item {
                                id: frame
                                x: (stage.contentWidth - width) / 2; y: (stage.contentHeight - height) / 2
                                visible: preview.imageWidth > 0 && preview.imageHeight > 0
                                width: Math.max(0, preview.imageWidth * stage.zoom)
                                height: Math.max(0, preview.imageHeight * stage.zoom)
                                clip: true
                                Image {
                                    source: editor.artwork.url
                                    autoTransform: true; smooth: editor.pixelScale < 2; mipmap: editor.pixelScale < 1
                                    // decode at full size once zoomed in, so details stay sharp
                                    sourceSize.width: editor.mag > 1 ? editor.artwork.width : 800
                                    width: editor.artwork.width * stage.zoom
                                    height: editor.artwork.height * stage.zoom
                                    x: -stage.offsetX * stage.zoom
                                    y: -stage.offsetY * stage.zoom
                                }
                            }
                            WheelHandler {
                                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                onWheel: function(event) {
                                    editor.zoomBy(event.angleDelta.y > 0 ? 1.25 : 0.8, stage, point.position.x - stage.contentX, point.position.y - stage.contentY)
                                }
                            }
                            TapHandler {
                                onDoubleTapped: function(eventPoint) {
                                    editor.setMag(editor.mag > 1 ? 1 : 1 / stage.fit, stage, eventPoint.position.x - stage.contentX, eventPoint.position.y - stage.contentY)
                                }
                            }
                            HoverHandler { cursorShape: editor.mag > 1 ? (stage.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.ArrowCursor }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Copy { text: editor.win.tr("cropPixels"); color: Theme.muted; Layout.fillWidth: true }
            Copy { text: editor.win.tr("cropLeft") }
            SpinBox { id: leftTrim; to: editor.artwork.width - 1; editable: true; Accessible.name: editor.win.tr("cropLeft") }
            Copy { text: editor.win.tr("cropRight") }
            SpinBox { id: rightTrim; to: editor.artwork.width - 1; editable: true; Accessible.name: editor.win.tr("cropRight") }
            Copy { text: editor.win.tr("cropTop") }
            SpinBox { id: topTrim; to: editor.artwork.height - 1; editable: true; Accessible.name: editor.win.tr("cropTop") }
            Copy { text: editor.win.tr("cropBottom") }
            SpinBox { id: bottomTrim; to: editor.artwork.height - 1; editable: true; Accessible.name: editor.win.tr("cropBottom") }
        }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { text: editor.win.tr("cropReset"); ghost: true; enabled: editor.changedCrop; onClicked: editor.setMargins(0, 0, 0, 0) }
            Item { Layout.fillWidth: true }
            ActionButton { text: editor.win.tr("cancel"); onClicked: editor.close() }
            ActionButton {
                text: editor.win.tr("cropApply"); primary: true
                enabled: editor.changedCrop && editor.cropWidth > 0 && editor.cropHeight > 0 && !editor.win.appView.busy
                onClicked: {
                    if (backend.metadata.applyCoverCrop(leftTrim.value, rightTrim.value, topTrim.value, bottomTrim.value))
                        editor.close()
                }
            }
        }
    }
}
