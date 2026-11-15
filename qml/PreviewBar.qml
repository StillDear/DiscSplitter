import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
// Chapter preview above the export bar. Audio mode: a slim player bar. Video mode: a tall panel with the
// picture on the left, and a near full-window "theater" view on double-click.
Item {
    id: bar
    required property var win
    readonly property bool active: win.previewView.previewRow >= 0
    readonly property bool video: win.previewView.previewVideo
    readonly property bool playing: player.playbackState === MediaPlayer.PlayingState
    readonly property bool loading: win.previewView.previewLoading
    readonly property real position: player.position
    readonly property real duration: player.duration
    readonly property bool seekable: player.seekable
    readonly property bool waveOn: backend.config.waveform !== false
    property bool theater: false
    property bool flush: false      // part of the workspace surface: square, with a hairline above instead of a frame
    readonly property string loadingText: win.tr(video ? "previewLoadingVideo" : "previewLoading")
    property real volume: 0.8
    property int lastRow: -1
    property int pendingSeek: -1
    // Where to start the next chapter's clip (a click on the timeline): {row, ms}
    property var startAt: null

    Layout.fillWidth: true
    // Video panel height: dragged live, else the saved share of the window, else the automatic size.
    property real heightLive: -1
    readonly property real ratio: (backend.config.layout || {}).preview_ratio || 0
    readonly property real minimumVideoHeight: 220     // picture, wave and controls still fit
    readonly property real maximumVideoHeight: Math.max(minimumVideoHeight, win.height - 480)   // the panels above keep ~340 px
    readonly property real videoHeight: Math.round(Math.max(minimumVideoHeight, Math.min(maximumVideoHeight,
        heightLive > 0 ? heightLive : ratio > 0 ? win.height * ratio : Math.min(400, Math.max(220, win.height * 0.35)))))
    Layout.preferredHeight: !active ? 0 : video ? videoHeight : 64
    // Never squeezed by the page above (it scrolls instead): the controls along the bottom stay in the window.
    Layout.minimumHeight: Layout.preferredHeight
    Behavior on Layout.preferredHeight {
        enabled: bar.heightLive < 0
        NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic }
    }
    clip: true
    visible: Layout.preferredHeight > 0

    function seek(ms) { if (player.seekable) player.position = ms }
    function toggle() {
        if (!active || win.previewView.previewUrl === "") return
        if (playing) player.pause()
        else {
            if (player.mediaStatus === MediaPlayer.EndOfMedia) player.position = 0
            player.play()
        }
    }
    // Whole seconds rounded as the chapter list rounds them: the length is the chapter's own (from the backend,
    // so it matches the list exactly), and the position never reads past it.
    readonly property int totalSeconds: win.previewView.previewLength > 0 ? win.previewView.previewLength
                                                                          : Math.round(player.duration / 1000)
    function clock(s) {
        s = Math.max(0, s)
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0")
    }
    function time(ms) { return clock(Math.min(totalSeconds, Math.round(ms / 1000))) }
    function total() { return clock(totalSeconds) }

    // A new clip for the same chapter (another audio track) keeps the position: easy A/B listening.
    readonly property string url: win.previewView.previewUrl
    onUrlChanged: {
        const sameChapter = win.previewView.previewRow === lastRow && player.source.toString() !== ""
        const wanted = startAt && startAt.row === win.previewView.previewRow ? startAt.ms : -1
        pendingSeek = wanted >= 0 ? wanted : sameChapter ? player.position : -1
        if (url !== "") startAt = null
        lastRow = win.previewView.previewRow
        player.source = url
        if (url !== "") player.play()
    }
    onActiveChanged: if (!active) { player.stop(); player.source = ""; lastRow = -1; theater = false }
    onVideoChanged: if (!video) theater = false
    onTheaterChanged: theater ? theaterView.open() : theaterView.close()

    MediaPlayer {
        id: player
        audioOutput: AudioOutput { volume: bar.volume }
        videoOutput: bar.theater ? bigPicture : panelPicture
        onMediaStatusChanged: {
            if ((mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia) && bar.pendingSeek > 0) {
                position = Math.min(bar.pendingSeek, Math.max(0, duration - 500))
                bar.pendingSeek = -1
            }
        }
    }

    // ---------- pieces shared by the three layouts
    component PlayButton: Button {
        id: playButton
        property int size: 38
        implicitWidth: size; implicitHeight: size; padding: 0
        enabled: !bar.loading && win.previewView.previewUrl !== ""
        onClicked: bar.toggle()
        Accessible.name: win.tr(bar.playing ? "previewPause" : "previewPlay")
        contentItem: Item {
            Icon { anchors.centerIn: parent; width: playButton.size * 0.42; height: width; kind: bar.playing ? "pause" : "play"; ink: Theme.accentInk }
        }
        background: Rectangle {
            radius: playButton.size / 2
            color: playButton.enabled ? (playButton.hovered ? Qt.lighter(Theme.accent, 1.08) : Theme.accent) : Theme.chip
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
    }
    component StepButtons: RowLayout {
        spacing: 2
        IconButton {
            iconKind: "prev"; enabled: win.previewView.previewRow > 0
            onClicked: backend.preview.previewStep(-1)
            ToolTip.visible: hovered; ToolTip.text: win.tr("previewPrev"); Accessible.name: win.tr("previewPrev")
        }
        PlayButton {}
        IconButton {
            iconKind: "next"; enabled: bar.active
            onClicked: backend.preview.previewStep(1)
            ToolTip.visible: hovered; ToolTip.text: win.tr("previewNext"); Accessible.name: win.tr("previewNext")
        }
    }
    component VolumeControl: RowLayout {
        // slim: the slider takes whatever width the row gives it (down to a short stub) instead of a fixed 84 px
        property bool slim: false
        spacing: 6
        Icon { kind: "volume"; ink: Theme.muted; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
        Slider {
            id: volumeSlider
            Layout.preferredWidth: 84; Layout.preferredHeight: 18; padding: 0
            Layout.fillWidth: parent.slim; Layout.minimumWidth: parent.slim ? 36 : 84
            from: 0; to: 1; value: bar.volume
            onMoved: bar.volume = value
            Accessible.name: win.tr("previewVolume")
            background: Rectangle {
                x: volumeSlider.leftPadding; y: (volumeSlider.height - height) / 2
                width: volumeSlider.availableWidth; height: 4; radius: 2; color: Theme.chip
                Rectangle { width: volumeSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: Theme.sub }
            }
            handle: Rectangle {
                x: volumeSlider.leftPadding + volumeSlider.visualPosition * (volumeSlider.availableWidth - width)
                y: (volumeSlider.height - height) / 2
                width: 10; height: 10; radius: 5; color: Theme.sub
            }
        }
    }
    component TrackSwitch: Segmented {
        visible: win.previewView.previewTracks.length > 1
        options: win.previewView.previewTracks.map(function(label, i) { return { key: String(i), label: label } })
        current: String(win.previewView.previewAudio)
        onPicked: function(key) { backend.preview.previewChapter(win.previewView.previewRow, Number(key)) }
    }
    // Seek bar with the clip's outline, a "preparing" shimmer and errors in the same place
    component Scrubber: Item {
        property real waveHeight: 18
        property color rest: Theme.line2
        implicitHeight: waveHeight
        WaveSeek {
            anchors.fill: parent
            visible: !bar.loading && win.previewView.previewError === ""
            peaks: backend.preview.previewWave; showWave: bar.waveOn
            position: player.position; duration: player.duration; interactive: player.seekable
            rest: parent.rest
            onMoved: function(ms) { player.position = ms }
        }
        Rectangle {
            visible: bar.loading; anchors.verticalCenter: parent.verticalCenter
            width: parent.width; height: 4; radius: 2; color: Theme.chip; clip: true
            Rectangle {
                id: sliver; width: parent.width * 0.25; height: parent.height; radius: 2; color: Theme.accent
                NumberAnimation on x {
                    running: bar.loading && Theme.animate; loops: Animation.Infinite
                    from: -sliver.width; to: sliver.parent.width; duration: 1100
                }
            }
        }
        Copy {
            visible: !bar.loading && win.previewView.previewError !== ""
            anchors.verticalCenter: parent.verticalCenter; width: parent.width
            text: win.playTr("previewFailed", bar.video).split("{e}").join(win.previewView.previewError)
            color: Theme.danger; font.pixelSize: Theme.px(11); elide: Text.ElideRight
        }
    }
    // Cut the chapter being played where the playhead is (the second part becomes a new, unnamed chapter).
    component SplitButton: IconButton {
        iconKind: "scissors"
        enabled: !bar.loading && win.previewView.previewUrl !== "" && !win.appView.busy && player.position >= 1000
        onClicked: backend.disc.splitChapter(win.previewView.previewRow, player.position / 1000)
        ToolTip.visible: hovered; ToolTip.delay: 300
        ToolTip.text: win.playTr("splitHere", bar.video) + (bar.video ? "\n" + win.tr("keyframeHint") : "")
        Accessible.name: win.playTr("splitHere", bar.video)
    }
    component CloseButton: IconButton {
        iconKind: "close"
        onClicked: backend.preview.stopPreview()
        ToolTip.visible: hovered; ToolTip.text: win.playTr("previewClose", bar.video); Accessible.name: win.playTr("previewClose", bar.video)
    }

    Rectangle {
        anchors.fill: parent
        radius: bar.flush ? 0 : 12; color: Theme.panel; border.color: bar.flush ? "transparent" : Theme.line
        Rectangle { visible: bar.flush; width: parent.width; height: 1; color: Theme.line }

        // ---------- audio mode: one row
        RowLayout {
            visible: !bar.video
            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 6
            StepButtons {}
            ColumnLayout {
                Layout.fillWidth: true; Layout.leftMargin: 8; Layout.minimumWidth: 160; spacing: 3
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Copy { text: win.previewView.previewTitle; font.weight: Font.DemiBold; elide: Text.ElideRight; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                    Copy {
                        visible: win.previewView.previewTracks.length <= 1
                        text: win.previewView.previewTrack; color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
                        elide: Text.ElideRight; Layout.maximumWidth: 260
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Copy { text: bar.time(player.position); font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(11); color: Theme.muted; Layout.preferredWidth: 40 }
                    Scrubber { Layout.fillWidth: true; waveHeight: bar.waveOn ? 22 : 18 }
                    Copy {
                        text: bar.loading ? bar.loadingText : bar.total()
                        font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(11); color: Theme.muted
                        Layout.preferredWidth: bar.loading ? implicitWidth : 40; horizontalAlignment: Text.AlignRight
                    }
                }
            }
            SplitButton { Layout.leftMargin: 4 }
            // At most a quarter of the row, so the waveform beside the title always keeps its room;
            // long track names shorten (the hint shows them whole).
            TrackSwitch {
                id: audioTracks
                Layout.leftMargin: 8; fill: true; Layout.minimumWidth: 0
                Layout.preferredWidth: Math.min(implicitWidth, 320, bar.width * 0.25)
                options: win.previewView.previewTracks.map(function(label, i) { return { key: String(i), label: label, hint: label } })
            }
            VolumeControl { Layout.leftMargin: 10; slim: true; Layout.preferredWidth: 106; Layout.minimumWidth: 60 }
            CloseButton { Layout.leftMargin: 4 }
        }

        // ---------- video mode: picture + controls
        RowLayout {
            visible: bar.video
            anchors.fill: parent; anchors.margins: 12; spacing: 16
            Rectangle {
                id: screen
                Layout.fillHeight: true; Layout.preferredWidth: Math.round(height * 16 / 9)
                // The controls beside it need ~230 px; only in a very narrow window does the picture give way
                Layout.maximumWidth: Math.min(parent.width * 0.62, parent.width - 16 - 230)
                radius: 8; color: "#000000"; clip: true
                VideoOutput { id: panelPicture; anchors.fill: parent; fillMode: VideoOutput.PreserveAspectFit }
                Copy {
                    anchors.centerIn: parent; visible: bar.loading || bar.theater
                    text: bar.loading ? bar.loadingText : win.tr("previewTheaterOn")
                    color: "#C9CED6"; font.pixelSize: Theme.px(13)
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: bar.toggle()
                    onDoubleClicked: bar.theater = true
                }
                IconButton {
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6
                    iconKind: "expand"; ink: "#FFFFFF"
                    opacity: hovered || screenHover.hovered ? 1 : 0.55
                    onClicked: bar.theater = true
                    background: Rectangle { radius: 8; color: Qt.rgba(0, 0, 0, parent.hovered ? 0.6 : 0.35) }
                    ToolTip.visible: hovered; ToolTip.text: win.tr("previewEnlarge"); Accessible.name: win.tr("previewEnlarge")
                }
                HoverHandler { id: screenHover }
            }
            // Beside the picture, which keeps its size: a narrow column, so every row stacks and shrinks
            // instead of sitting side by side. Top: title and close, the track, the audio switch on a line
            // of its own. Bottom: the waveform across the full width, the times under it, then the buttons
            // with the volume. No row needs more than ~220 px, so nothing is pushed out of view.
            ColumnLayout {
                id: side
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0; spacing: 0
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 3
                        Copy { text: win.previewView.previewTitle; font.pixelSize: Theme.heading; font.weight: Theme.strong; elide: Text.ElideRight; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                        Copy { text: win.previewView.previewTrack; color: Theme.muted; font.pixelSize: Theme.px(12); elide: Text.ElideRight; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                    }
                    CloseButton { Layout.alignment: Qt.AlignTop }
                }
                // Audio track: a full-width switch; long names shorten (the hint shows them whole)
                TrackSwitch {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.topMargin: 12
                    fill: true; itemHeight: Math.round(26 * Math.max(1, Theme.fontScale))
                    options: win.previewView.previewTracks.map(function(label, i) { return { key: String(i), label: label, hint: label } })
                }
                Item { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 10 }
                Scrubber {
                    Layout.fillWidth: true; Layout.preferredHeight: waveHeight
                    waveHeight: bar.waveOn ? Math.round(Math.max(32, Math.min(64, bar.height * 0.2))) : 18
                }
                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: 4; spacing: 8
                    visible: !bar.loading           // the picture says it is being prepared
                    Copy {
                        text: bar.time(player.position); font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.caption; color: Theme.muted
                        wrapMode: Text.NoWrap
                    }
                    Item { Layout.fillWidth: true }
                    Copy {
                        text: bar.total(); font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.caption; color: Theme.muted
                        wrapMode: Text.NoWrap
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; Layout.topMargin: 8; spacing: 6
                    StepButtons {}
                    SplitButton { Layout.leftMargin: 4 }
                    Item { Layout.fillWidth: true; Layout.minimumWidth: 4 }
                    VolumeControl { Layout.maximumWidth: 120; Layout.fillWidth: true; Layout.minimumWidth: 60; slim: true }
                }
            }
        }
    }

    // ---------- theater: near full-window picture
    Popup {
        id: theaterView
        parent: Overlay.overlay
        x: 0; y: 0; width: parent ? parent.width : 0; height: parent ? parent.height : 0
        modal: true; focus: true; padding: 24
        closePolicy: Popup.CloseOnEscape
        onClosed: bar.theater = false
        background: Rectangle { color: "#050608" }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }
        ColumnLayout {
            anchors.fill: parent; spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Copy { text: win.previewView.previewTitle; color: "#FFFFFF"; font.pixelSize: Theme.title; font.weight: Theme.strong; Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                Copy { text: win.previewView.previewTrack; color: "#9BA3AE"; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                IconButton {
                    iconKind: "shrink"; ink: "#FFFFFF"; Layout.leftMargin: 8
                    onClicked: bar.theater = false
                    background: Rectangle { radius: 8; color: parent.hovered ? Qt.rgba(1, 1, 1, 0.12) : "transparent" }
                    ToolTip.visible: hovered; ToolTip.text: win.tr("previewShrink"); Accessible.name: win.tr("previewShrink")
                }
            }
            Item {
                Layout.fillWidth: true; Layout.fillHeight: true
                VideoOutput { id: bigPicture; anchors.fill: parent; fillMode: VideoOutput.PreserveAspectFit }
                MouseArea { anchors.fill: parent; onClicked: bar.toggle(); onDoubleClicked: bar.theater = false }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                StepButtons {}
                Copy { text: bar.time(player.position); color: "#C9CED6"; font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(12) }
                Scrubber { Layout.fillWidth: true; waveHeight: bar.waveOn ? 44 : 18; rest: Qt.rgba(1, 1, 1, 0.22) }
                Copy { text: bar.total(); color: "#C9CED6"; font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(12) }
                VolumeControl {}
            }
        }
    }
}
