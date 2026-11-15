import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: page
    required property var win
    property int selectedChapter: -1
    // One surface for the whole workspace, filling the window; its three sections are divided by hairlines.
    color: Theme.panel; clip: true
    // Panel widths: dragged live (…Live), otherwise the saved layout, otherwise the default.
    readonly property var layoutSizes: backend.config.layout || ({})
    readonly property int centerMinimum: 420
    // A saved width never squeezes the middle panel when the window is narrower than when it was set.
    function fit(value, share) { return Math.max(200, Math.min(value, (win.width - 24) * share)) }
    property real leftLive: -1
    property real rightLive: -1
    readonly property real leftWidth: leftLive > 0 ? leftLive : fit(layoutSizes.work_left || 268, 0.32)
    // Music is the norm: the content column appears only once some chapter is talk or unsure.
    // Settings → Preview decides: "auto" shows it once some chapter is talk or unsure, "show" always (once the
    // waveform has been read), "hide" never.
    readonly property string kindMode: backend.config.kind_column || "show"
    readonly property var kindValues: Object.values(win.discView.chapterKinds || {})
    readonly property var kindManual: win.discView.chapterKindsManual || []
    readonly property bool kindsShown: kindMode === "show" ? kindValues.length > 0
                                     : kindMode === "auto" && kindValues.some(function(k) { return k !== "music" })
    readonly property bool originsShown: !!win.discView.originsMixed
    readonly property real rightWidth: rightLive > 0 ? rightLive : fit(layoutSizes.work_right || 312, 0.36)

    // Merge / split / move one chapter. One menu for every row; `row` says which.
    function openChapterMenu(row, seconds, item, x, y) {
        selectedChapter = row
        chapterMenu.row = row
        chapterMenu.seconds = seconds
        chapterMenu.popup(item, x, y)
    }
    // Up / Down in a title field: carry on typing in the row above or below.
    function editTitleAt(row) {
        if (row < 0 || row >= chapterList.count) return
        selectedChapter = row
        chapterList.positionViewAtIndex(row, ListView.Contain)
        const item = chapterList.itemAtIndex(row)
        if (!item) return
        item.titleField.forceActiveFocus()
        item.titleField.cursorPosition = item.titleField.length
    }
    // An edit resets the chapter model; scroll once the view has laid the new rows out,
    // or the jump is lost (the reset puts the view back at the top).
    function afterEdit(row) {
        selectedChapter = Math.max(0, Math.min(row, chapterList.count - 1))
        Qt.callLater(function() { chapterList.positionViewAtIndex(page.selectedChapter, ListView.Contain) })
    }
    // Music / talk by hand, from the content column
    AppMenu {
        id: kindMenu
        property int row: -1
        property int number: 0
        property string kind: ""
        AppMenuItem { text: win.tr("kind_music"); checkable: true; checked: kindMenu.kind === "music"; onTriggered: backend.disc.setChapterKind(kindMenu.row, "music") }
        AppMenuItem { text: win.tr("kind_interlude"); checkable: true; checked: kindMenu.kind === "interlude"; onTriggered: backend.disc.setChapterKind(kindMenu.row, "interlude") }
        AppMenuItem { text: win.tr("kind_talk"); checkable: true; checked: kindMenu.kind === "talk"; onTriggered: backend.disc.setChapterKind(kindMenu.row, "talk") }
        MenuSeparator { topPadding: 4; bottomPadding: 4; contentItem: Rectangle { implicitHeight: 1; color: Theme.line } }
        AppMenuItem { text: win.tr("kindAuto"); enabled: page.kindManual.indexOf(kindMenu.number) >= 0; onTriggered: backend.disc.setChapterKind(kindMenu.row, "") }
    }
    AppMenu {
        id: chapterMenu
        property int row: -1
        property real seconds: 0
        readonly property bool previewingRow: row === win.previewView.previewRow && win.previewView.previewUrl !== ""
        minWidth: 240
        AppMenuItem {
            text: win.playTr(chapterMenu.previewingRow ? "splitHere" : "splitHereHint", win.videoMode)
            enabled: chapterMenu.previewingRow
            onTriggered: { const r = chapterMenu.row; backend.disc.splitChapter(r, win.previewPosition / 1000); page.afterEdit(r) }
        }
        AppMenuItem {
            text: win.tr("splitMiddle")
            onTriggered: { const r = chapterMenu.row; backend.disc.splitChapter(r, chapterMenu.seconds / 2); page.afterEdit(r) }
        }
        MenuSeparator { topPadding: 4; bottomPadding: 4; contentItem: Rectangle { implicitHeight: 1; color: Theme.line } }
        AppMenuItem {
            text: win.tr("mergePrevious"); enabled: chapterMenu.row > 0
            onTriggered: { const r = chapterMenu.row - 1; backend.disc.mergeChapterWithNext(r); page.afterEdit(r) }
        }
        AppMenuItem {
            text: win.tr("mergeNext"); enabled: chapterMenu.row >= 0 && chapterMenu.row < chapterList.count - 1
            onTriggered: { const r = chapterMenu.row; backend.disc.mergeChapterWithNext(r); page.afterEdit(r) }
        }
        MenuSeparator { topPadding: 4; bottomPadding: 4; contentItem: Rectangle { implicitHeight: 1; color: Theme.line } }
        AppMenuItem {
            text: win.tr("nudgeEarlier"); enabled: chapterMenu.row > 0
            onTriggered: { const r = chapterMenu.row; backend.disc.nudgeChapterStart(r, -0.5); page.afterEdit(r) }
        }
        AppMenuItem {
            text: win.tr("nudgeLater"); enabled: chapterMenu.row > 0
            onTriggered: { const r = chapterMenu.row; backend.disc.nudgeChapterStart(r, 0.5); page.afterEdit(r) }
        }
        MenuSeparator { topPadding: 4; bottomPadding: 4; contentItem: Rectangle { implicitHeight: 1; color: Theme.line } }
        AppMenuItem {
            text: win.tr("restoreChapters"); enabled: win.discView.chaptersEdited
            onTriggered: { backend.disc.restoreChapters(); page.afterEdit(0) }
        }
    }

    RowLayout {
        id: columns
        anchors.fill: parent; spacing: 0
        // ---------- Left: disc + playlists ----------
        Card {
            flat: true
            Layout.preferredWidth: page.leftWidth; Layout.fillHeight: true
            // Like the streams column: every candidate stays readable and the column scrolls as a whole when short.
            Flickable {
                id: discFlick
                anchors.fill: parent; clip: true
                contentWidth: width; contentHeight: discColumn.height
                boundsBehavior: Flickable.StopAtBounds; interactive: contentHeight > height
                ScrollBar.vertical: SlimScrollBar { id: discBar }
            ColumnLayout {
                id: discColumn
                width: discFlick.width - discBar.gutter; height: Math.max(discFlick.height, implicitHeight); spacing: 16
                // What the workspace produces: video chapters or audio tracks. Short labels when the
                // column is too narrow for the full ones (measured off screen, so the switch never flickers).
                RowLayout {
                    id: modeRow
                    Layout.fillWidth: true; spacing: 8
                    Segmented {
                        id: modeMeasure
                        visible: false; itemHeight: Math.round(30 * Math.max(1, Theme.fontScale))
                        options: [{ key: "mkv", label: win.tr("modeVideo") }, { key: "flac", label: win.tr("modeAudio") }]
                    }
                    Segmented {
                        readonly property bool short: modeRow.width - (busyMark.visible ? busyMark.width + 8 : 0) < modeMeasure.implicitWidth
                        Layout.fillWidth: true; fill: true; itemHeight: Math.round(30 * Math.max(1, Theme.fontScale))
                        options: short
                            ? [{ key: "mkv", label: win.tr("modeVideoShort") }, { key: "flac", label: win.tr("modeAudioShort") }]
                            : [{ key: "mkv", label: win.tr("modeVideo") }, { key: "flac", label: win.tr("modeAudio") }]
                        current: win.discView.outputFormat
                        enabled: !win.appView.busy
                        onPicked: function(key) { backend.disc.setOutputFormat(key) }
                        HoverHandler { id: modeHover }
                        ToolTip.visible: modeHover.hovered && short; ToolTip.delay: 400
                        ToolTip.text: win.tr(win.discView.outputFormat === "flac" ? "modeAudio" : "modeVideo")
                    }
                    BusyIndicator {
                        id: busyMark
                        running: win.appView.working && !win.appView.pipeline; visible: running
                        Layout.preferredWidth: 20; Layout.preferredHeight: 20
                        ToolTip.visible: running && busyHover.hovered; ToolTip.text: win.tr(win.appView.status)
                        HoverHandler { id: busyHover }
                    }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; Layout.topMargin: -4; color: Theme.line }
                RowLayout {
                    spacing: 12
                    Icon {
                        id: discIcon; kind: "disc"; ink: Theme.muted
                        Layout.preferredWidth: 28; Layout.preferredHeight: 28; Layout.alignment: Qt.AlignTop
                        // Spins while the disc is being scanned or chapters are read.
                        RotationAnimation on rotation {
                            running: Theme.animate && win.appView.working && !win.appView.pipeline
                            from: 0; to: 360; duration: 1400; loops: Animation.Infinite
                            onRunningChanged: if (!running) discIcon.rotation = 0
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Copy { text: win.discView.album || win.tr("source"); font.pixelSize: Theme.px(15); font.bold: true; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                        Copy { text: win.discView.artist; color: Theme.muted; Layout.fillWidth: true; visible: text !== "" }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    Copy { text: win.discView.source; font.family: Theme.mono; font.pixelSize: Theme.px(11); color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere; maximumLineCount: 3; elide: Text.ElideMiddle; lineHeight: 1.2 }
                    Copy { visible: text !== ""; text: win.discView.sourceSummary || ""; font.pixelSize: Theme.px(12); color: Theme.sub; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                    RowLayout {
                        spacing: 8
                        ActionButton {
                            id: changeSourceButton
                            text: win.tr("changeFolder"); Layout.fillWidth: true; enabled: !win.appView.working
                            onClicked: sourceMenu.popup(changeSourceButton, 0, changeSourceButton.height + 4)
                            AppMenu {
                                id: sourceMenu
                                minWidth: 180
                                AppMenuItem { text: win.tr("sourceFolder"); onTriggered: win.openFolder("source") }
                                AppMenuItem { text: win.tr("sourceFile"); onTriggered: win.openSourceFile() }
                            }
                        }
                        ActionButton { text: win.tr("rescan"); Layout.fillWidth: true; enabled: !win.appView.working; onClicked: backend.disc.scan() }
                    }
                }
                SectionTitle { text: win.tr("playlist"); note: win.fmt("candidateCount", { n: playlistList.count }); Layout.fillWidth: true }
                ListView {
                    id: playlistList
                    // As tall as its candidates; the column itself scrolls when they do not fit.
                    Layout.fillWidth: true; Layout.preferredHeight: contentHeight
                    interactive: false; spacing: 8; model: playlistModel
                    populate: ListEnter {}
                    add: ListEnter {}
                    delegate: Rectangle {
                        id: pl
                        required property int index
                        required property string label
                        required property string detail
                        required property string tracks
                        required property string headline
                        required property string reasons
                        required property bool chosen
                        width: ListView.view.width; height: plInfo.implicitHeight + 24
                        radius: 10
                        color: chosen ? Theme.accentSoft : (plHover.hovered ? Qt.lighter(Theme.raised, Theme.light ? 0.98 : 1.1) : Theme.raised)
                        border.color: chosen ? Theme.accent : Theme.line
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
                        HoverHandler { id: plHover }
                        ToolTip.visible: plHover.hovered && pl.reasons !== ""; ToolTip.delay: 600; ToolTip.text: pl.reasons
                        ColumnLayout {
                            id: plInfo; x: 12; y: 12; width: parent.width - 24; spacing: 8
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Copy { text: pl.label; font.family: Theme.mono; font.weight: Font.Medium; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight; color: pl.chosen ? Theme.text : Theme.sub }
                                Copy { visible: pl.index === 0; text: win.tr("recommended"); font.pixelSize: Theme.px(12); color: Theme.accentText; wrapMode: Text.NoWrap }
                            }
                            Copy { text: pl.detail; font.pixelSize: Theme.px(12); color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                            // Every candidate: its streams, so the candidates can be compared at a glance.
                            Copy { visible: pl.tracks !== ""; text: pl.tracks; font.pixelSize: Theme.px(12); color: Theme.muted; Layout.fillWidth: true; lineHeight: 1.3 }
                            // Only the chosen playlist explains itself; the others keep to name, length and chapters.
                            Copy { visible: pl.chosen && pl.headline !== ""; text: pl.headline; font.pixelSize: Theme.px(12); color: Theme.sub; Layout.fillWidth: true; lineHeight: 1.3 }
                        }
                        MouseArea { anchors.fill: parent; enabled: !win.appView.working; cursorShape: Qt.PointingHandCursor; onClicked: backend.disc.selectPlaylist(pl.index) }
                    }
                }
                ColumnLayout {
                    visible: win.discView.sidecars.length > 0; Layout.fillWidth: true; spacing: 6
                    Copy { text: win.tr("sidecars"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true }
                    Repeater {
                        model: win.discView.sidecars.slice(0, 3)
                        ActionButton { required property string modelData; Layout.fillWidth: true; text: modelData.split(/[\\/]/).pop(); enabled: !win.appView.working; onClicked: backend.names.importFile(modelData) }
                    }
                }
                // Recent exports: open the folder, or load that disc again
                ColumnLayout {
                    visible: (win.appView.recentExports || []).length > 0
                    Layout.fillWidth: true; spacing: 4
                    SectionTitle { text: win.tr("recentTitle"); Layout.fillWidth: true }
                    Repeater {
                        model: win.appView.recentExports || []
                        AbstractButton {
                            id: recentItem
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true; implicitHeight: recentRow.implicitHeight + 10; hoverEnabled: true
                            Accessible.name: modelData.album
                            onClicked: backend.disc.openRecent(index)
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            ToolTip.visible: hovered; ToolTip.delay: 500; ToolTip.text: modelData.folder
                            background: Rectangle { radius: 8; color: recentItem.hovered ? Theme.raised : "transparent" }
                            contentItem: Item {
                                RowLayout {
                                    id: recentRow; x: 6; y: 5; width: parent.width - 6; spacing: 4
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 1
                                        Copy { text: recentItem.modelData.album; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                                        Copy { text: recentItem.modelData.detail; font.pixelSize: Theme.px(11); color: Theme.faint; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                                    }
                                    IconButton {
                                        visible: recentItem.modelData.canReload
                                        iconKind: "refresh"; implicitWidth: 26; implicitHeight: 24; enabled: !win.appView.working
                                        onClicked: backend.disc.reloadRecent(recentItem.index)
                                        ToolTip.visible: hovered; ToolTip.delay: 300; ToolTip.text: win.tr("recentReload")
                                        Accessible.name: win.tr("recentReload")
                                    }
                                }
                            }
                        }
                    }
                }
                Item { Layout.fillHeight: true; Layout.fillWidth: true; Layout.preferredHeight: 0 }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
                // All tools found: one quiet line. Something missing: the full list, so it can be fixed.
                RowLayout {
                    visible: !win.appView.toolMissing
                    Layout.fillWidth: true; spacing: 8
                    Rectangle { Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4; color: Theme.good }
                    Copy { text: win.tr("toolsAllFound"); font.pixelSize: Theme.px(12); color: Theme.muted; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                    HoverHandler { id: toolsHover }
                    ToolTip.visible: toolsHover.hovered; ToolTip.delay: 400
                    ToolTip.text: "mkvmerge · mkvextract · ffmpeg · ffprobe"
                }
                ColumnLayout {
                    visible: !!win.appView.toolMissing
                    Layout.fillWidth: true; spacing: 5
                    Repeater {
                        model: toolModel
                        RowLayout {
                            required property string tool
                            required property bool available
                            spacing: 8
                            Rectangle { Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4; color: available ? Theme.good : "transparent"; border.color: available ? Theme.good : Theme.danger }
                            Copy { text: tool; font.pixelSize: Theme.px(12); color: Theme.muted; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                            Copy { text: win.tr(available ? "found" : "missing"); font.pixelSize: Theme.px(12); color: available ? Theme.muted : Theme.danger; wrapMode: Text.NoWrap }
                        }
                    }
                }
            }
            }
        }

        Splitter {
            Layout.fillHeight: true; Layout.leftMargin: -6; Layout.rightMargin: -6; z: 1; divider: true
            size: page.leftWidth; direction: 1; minimum: 200; maximum: Math.min(480, page.width - page.rightWidth - page.centerMinimum - 24)
            onResized: function(value) { page.leftLive = value }
            onCommitted: function(value) { backend.setLayoutSize("work_left", value); page.leftLive = -1 }
            onReset: backend.setLayoutSize("work_left", -1)
        }
        // ---------- Center: chapters ----------
        Card {
            flat: true
            Layout.fillWidth: true; Layout.fillHeight: true; padding: 20
            ColumnLayout {
                id: centerColumn
                anchors.fill: parent; spacing: 14
                // Header: title, count and "Get titles" on one line; the selection buttons sit between them when there is
                // room, otherwise on a line of their own. Nothing is cut short.
                Item {
                    id: chapterHeader
                    readonly property real topHeight: Math.max(chapterTitle.implicitHeight, sourceBar.implicitHeight)
                    readonly property bool inline: width >= chapterTitle.implicitWidth + countBadge.implicitWidth + selectRow.implicitWidth
                                                            + sourceBar.implicitWidth + 3 * 10 + 16
                    Layout.fillWidth: true
                    implicitHeight: inline ? topHeight : topHeight + 8 + selectRow.implicitHeight
                    RowLayout {
                        anchors.left: parent.left; anchors.right: parent.right; height: chapterHeader.topHeight; spacing: 10
                        Copy { id: chapterTitle; text: win.tr("chapters"); font.pixelSize: Theme.px(20); font.bold: true; wrapMode: Text.NoWrap }
                        Badge { id: countBadge; tone: "good"; text: win.fmt("chapterCount", { n: chapterList.count }); visible: chapterList.count > 0 }
                        Item { Layout.fillWidth: true }
                        ActionButton {
                            id: sourceBar
                            text: win.tr("getTitles"); selected: true; enabled: !win.appView.working && chapterList.count > 0
                            onClicked: backend.names.openTitles()
                        }
                    }
                    RowLayout {
                        id: selectRow
                        spacing: 6
                        x: chapterHeader.inline ? countBadge.x + countBadge.width + 10 : 0
                        y: chapterHeader.inline ? (chapterHeader.topHeight - height) / 2 : chapterHeader.topHeight + 8
                        ActionButton {
                            readonly property bool allSelected: win.discView.chapterSelected === chapterList.count
                            text: win.tr(allSelected ? "selectNone" : "selectAll")
                            implicitHeight: 28; enabled: !win.appView.busy && chapterList.count > 0
                            onClicked: backend.disc.setAllChapters(!allSelected)
                        }
                        ActionButton {
                            text: win.tr("selectRenamed")
                            implicitHeight: 28
                            enabled: !win.appView.busy && win.discView.unnamedRows.length < chapterList.count
                            onClicked: backend.disc.selectRenamedChapters()
                        }
                        ActionButton {
                            text: win.tr("unselectUnnamed")
                            implicitHeight: 28
                            enabled: !win.appView.busy && win.discView.chapterSelected > 0 && win.discView.unnamedRows.length > 0
                            onClicked: backend.disc.unselectUnnamedChapters()
                        }
                    }
                }

                // Timeline
                Rectangle {
                    id: timeline
                    readonly property bool waveOn: backend.config.waveform !== false
                    readonly property bool waveShown: waveOn && win.previewView.waveState === "ready" && backend.preview.waveform.length > 1
                    // With few chapters the list leaves room below it: the waveform takes part of that room.
                    readonly property real spare: centerColumn.height - chapterHeader.height - listHeader.height
                                                  - centerColumn.spacing * 3 - chapterList.contentHeight - 96
                    Layout.fillWidth: true; radius: 10; color: Theme.deep; border.color: Theme.line
                    Layout.preferredHeight: waveShown ? Math.round(Math.max(96, Math.min(220, 96 + spare * 0.6))) : 76
                    Behavior on Layout.preferredHeight { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 6
                        RowLayout {
                            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 3
                            Repeater {
                                model: chapterModel
                                Rectangle {
                                    id: segment
                                    required property int index
                                    required property real seconds
                                    required property real begin
                                    required property int number
                                    required property string title
                                    readonly property bool on: index === page.selectedChapter
                                    readonly property bool unnamed: title.trim() === ""
                                    readonly property bool previewing: index === win.previewView.previewRow
                                    Layout.fillWidth: true; Layout.preferredWidth: Math.max(1, seconds); Layout.fillHeight: true
                                    radius: 6; color: on ? Theme.accent : unnamed ? Theme.pendingBg : Theme.chip
                                    clip: true
                                    Behavior on color { ColorAnimation { duration: Theme.normal } }
                                    // This chapter's slice of the whole-programme outline (2 peaks per second)
                                    Canvas {
                                        id: segmentWave
                                        anchors.fill: parent; anchors.topMargin: 4; anchors.bottomMargin: 4
                                        visible: timeline.waveShown
                                        readonly property color ink: segment.on ? Theme.accentInk : segment.unnamed ? Theme.pendingText : Theme.muted
                                        opacity: segment.on ? 0.55 : 0.6
                                        onPaint: {
                                            const ctx = getContext("2d")
                                            ctx.reset()
                                            const all = backend.preview.waveform
                                            if (!visible || !all || all.length < 2 || width <= 0) return
                                            const a = Math.max(0, Math.floor(segment.begin * 2))
                                            const b = Math.min(all.length, Math.max(a + 1, Math.ceil((segment.begin + segment.seconds) * 2)))
                                            const n = b - a
                                            if (n < 1) return
                                            const step = 2, bars = Math.max(1, Math.floor(width / step)), mid = height / 2
                                            ctx.fillStyle = ink
                                            for (let i = 0; i < bars; i++) {
                                                const p = a + Math.floor(i * n / bars), q = Math.max(p + 1, a + Math.floor((i + 1) * n / bars))
                                                let m = 0
                                                for (let j = p; j < q && j < b; j++) if (all[j] > m) m = all[j]
                                                const h = Math.max(1, Math.sqrt(m) * height)
                                                ctx.fillRect(i * step, mid - h / 2, 1.2, h)
                                            }
                                        }
                                        onVisibleChanged: requestPaint()
                                        onWidthChanged: requestPaint()
                                        onHeightChanged: requestPaint()
                                        onInkChanged: requestPaint()
                                        Connections { target: backend.preview; function onWaveChanged() { segmentWave.requestPaint() } }
                                    }
                                    Rectangle {
                                        visible: timeline.waveShown && numberLabel.visible
                                        x: 3; y: 3; width: numberLabel.implicitWidth + 6; height: numberLabel.implicitHeight + 2; radius: 4
                                        color: segment.color; opacity: 0.85
                                    }
                                    Text {
                                        id: numberLabel
                                        x: timeline.waveShown ? 6 : (parent.width - width) / 2
                                        y: timeline.waveShown ? 4 : (parent.height - height) / 2
                                        text: number.toString().padStart(2, "0"); font.family: Theme.mono; font.pixelSize: Theme.px(11)
                                        color: parent.on ? Theme.accentInk : parent.unnamed ? Theme.pendingText : Theme.muted; visible: parent.width > 22
                                    }
                                    // Where the preview is playing
                                    Rectangle {
                                        visible: segment.previewing && win.previewView.previewUrl !== "" && segment.seconds > 0
                                        x: Math.min(parent.width - width, Math.max(0, win.previewPosition / 1000 / segment.seconds * parent.width))
                                        width: 2; height: parent.height
                                        color: segment.on ? Theme.accentInk : Theme.accent
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: { page.selectedChapter = parent.index; chapterList.positionViewAtIndex(parent.index, ListView.Contain) } }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Copy { text: "0:00:00"; font.family: Theme.mono; font.pixelSize: Theme.px(11); color: Theme.faint; wrapMode: Text.NoWrap }
                            // Waveform: quick on/off, and how far the background read has got
                            Rectangle {
                                implicitWidth: waveToggle.implicitWidth + 16; implicitHeight: 20; radius: 10
                                visible: chapterList.count > 0
                                color: timeline.waveOn ? Theme.accentSoft : "transparent"
                                border.color: timeline.waveOn ? "transparent" : Theme.line2
                                RowLayout {
                                    id: waveToggle; anchors.centerIn: parent; spacing: 4
                                    Icon { kind: "wave"; ink: timeline.waveOn ? Theme.accent : Theme.faint; Layout.preferredWidth: 12; Layout.preferredHeight: 12 }
                                    Copy { text: win.tr("waveform"); font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap; color: timeline.waveOn ? Theme.accent : Theme.faint }
                                }
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                                    onClicked: backend.setPreference("waveform", timeline.waveOn ? "false" : "true")
                                    ToolTip.visible: containsMouse; ToolTip.text: win.tr("waveformHint")
                                }
                                Accessible.role: Accessible.CheckBox; Accessible.name: win.tr("waveform"); Accessible.checked: timeline.waveOn
                            }
                            Copy {
                                visible: timeline.waveOn && (win.previewView.waveState === "computing" || win.previewView.waveState === "failed")
                                text: win.previewView.waveState === "failed" ? win.tr("waveFailed") : win.fmt("waveComputing", { p: win.previewView.waveProgress })
                                color: win.previewView.waveState === "failed" ? Theme.danger : Theme.faint
                                font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap
                            }
                            Rectangle {
                                visible: win.discView.chaptersEdited
                                implicitWidth: editedRow.implicitWidth + 16; implicitHeight: 20; radius: 10
                                color: Theme.accentSoft
                                RowLayout {
                                    id: editedRow; anchors.centerIn: parent; spacing: 4
                                    Icon { kind: "scissors"; ink: Theme.accentText; Layout.preferredWidth: 12; Layout.preferredHeight: 12 }
                                    Copy {
                                        text: win.tr("restoreChapters")
                                        font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap; color: Theme.accentText
                                        font.underline: editedArea.containsMouse
                                    }
                                }
                                MouseArea {
                                    id: editedArea
                                    anchors.fill: parent; hoverEnabled: true; enabled: !win.appView.busy
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: { backend.disc.restoreChapters(); page.afterEdit(0) }
                                    ToolTip.visible: containsMouse; ToolTip.delay: 300
                                    ToolTip.text: win.discView.keepVideo && win.discView.outputFormat === "mkv" ? win.tr("keyframeHint") : win.tr("restoreChapters")
                                }
                                Accessible.role: Accessible.Button; Accessible.name: win.tr("restoreChapters")
                            }
                            Item { Layout.fillWidth: true }
                            // Legend: how many chapters still need a name; click to jump to the next one.
                            Item {
                                visible: chapterList.count > 0
                                implicitWidth: legend.implicitWidth; implicitHeight: legend.implicitHeight
                                readonly property var rows: win.discView.unnamedRows || []
                                RowLayout {
                                    id: legend; spacing: 6
                                    Rectangle {
                                        Layout.preferredWidth: 10; Layout.preferredHeight: 10; radius: 3
                                        color: parent.parent.rows.length ? Theme.pendingBg : Theme.goodBg
                                        border.color: parent.parent.rows.length ? Theme.pendingText : Theme.good; border.width: 1
                                    }
                                    Copy {
                                        text: parent.parent.rows.length ? win.fmt("unnamedCount", { n: parent.parent.rows.length }) : win.tr("allNamed")
                                        font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap
                                        color: parent.parent.rows.length ? Theme.pendingText : Theme.goodText
                                        font.underline: legendArea.containsMouse && parent.parent.rows.length > 0
                                    }
                                }
                                MouseArea {
                                    id: legendArea; anchors.fill: parent; hoverEnabled: true
                                    enabled: parent.rows.length > 0
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    ToolTip.visible: containsMouse && enabled; ToolTip.text: win.tr("nextUnnamed")
                                    onClicked: {
                                        const rows = parent.rows
                                        const later = rows.filter(function(r) { return r > page.selectedChapter })
                                        const next = later.length ? later[0] : rows[0]
                                        page.selectedChapter = next
                                        chapterList.positionViewAtIndex(next, ListView.Center)
                                    }
                                }
                            }
                        }
                    }
                }

                RowLayout {
                    id: listHeader
                    Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12 + chapterBar.gutter; spacing: 12
                    Item { Layout.preferredWidth: 30 }
                    Item { Layout.preferredWidth: 28 }
                    Copy { text: "#"; Layout.preferredWidth: 26; color: Theme.faint; font.pixelSize: Theme.px(12) }
                    Copy { text: win.tr("startTime"); Layout.preferredWidth: 64; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                    Copy { text: win.tr("titleColumn"); Layout.fillWidth: true; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                    // "Content" is a guess: an asterisk-like mark and the reason on hover
                    Copy {
                        visible: page.kindsShown; text: win.tr("kindColumn") + "*"; Layout.preferredWidth: 64
                        horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
                        HoverHandler { id: kindHeaderHover }
                        ToolTip.visible: kindHeaderHover.hovered; ToolTip.delay: 200; ToolTip.text: win.tr("kindHint")
                    }
                    Copy { text: win.tr("duration"); Layout.preferredWidth: 52; horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                    Copy { visible: page.originsShown; text: win.tr("origin"); Layout.preferredWidth: 64; horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                    Item { Layout.preferredWidth: 28 }
                }
                ListView {
                    id: chapterList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 2; model: chapterModel
                    ScrollBar.vertical: SlimScrollBar { id: chapterBar }
                    // No populate/add transition here: every chapter edit resets this model, and a
                    // populate transition still running while the view scrolls to the edited row
                    // left rows stacked on top of each other.
                    delegate: Rectangle {
                        id: chapterRow
                        required property int index
                        required property int number
                        required property string title
                        required property string duration
                        required property string start
                        required property string origin
                        required property bool included
                        required property real seconds
                        readonly property bool on: index === page.selectedChapter
                        readonly property bool previewing: index === win.previewView.previewRow
                        property alias titleField: titleField
                        width: ListView.view.width - chapterBar.gutter; height: Theme.rowHeight; radius: 8
                        color: previewing ? Theme.accentSoft : on ? Theme.raised : "transparent"
                        HoverHandler { id: chapterHover }
                        TapHandler {
                            acceptedButtons: Qt.RightButton; enabled: !win.appView.busy
                            onTapped: function(point) { page.openChapterMenu(chapterRow.index, chapterRow.seconds, chapterRow, point.position.x, point.position.y) }
                        }
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 12
                            CheckBox {
                                id: chapterCheck
                                checked: chapterRow.included; enabled: !win.appView.busy
                                Layout.preferredWidth: 30; Layout.preferredHeight: 28; padding: 0
                                Accessible.name: win.fmt("chapterN", { n: chapterRow.number })
                                indicator: SelectionMark { anchors.centerIn: parent; checked: chapterCheck.checked }
                                onClicked: backend.disc.setChapterIncluded(chapterRow.index, checked)
                            }
                            IconButton {
                                id: listenButton
                                readonly property bool playingHere: chapterRow.previewing && win.previewPlaying
                                iconKind: playingHere ? "pause" : "play"
                                implicitWidth: 28; implicitHeight: 28; Layout.preferredWidth: 28
                                enabled: !win.appView.busy && audioList.count > 0
                                ink: chapterRow.previewing ? Theme.accentText : hovered ? Theme.text : Theme.muted
                                opacity: !enabled ? 0.25 : chapterRow.previewing || chapterHover.hovered || hovered || visualFocus ? 1 : 0.35
                                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                                onClicked: {
                                    page.selectedChapter = chapterRow.index
                                    if (chapterRow.previewing && win.previewView.previewUrl !== "") win.togglePreview()
                                    else backend.preview.previewChapter(chapterRow.index, -1)
                                }
                                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.playTr("listenChapter", win.videoMode)
                                Accessible.name: win.playTr("listenChapter", win.videoMode) + " " + chapterRow.number
                            }
                            Copy { text: chapterRow.number.toString().padStart(2, "0"); font.family: Theme.mono; font.weight: Font.Medium; color: chapterRow.on ? Theme.accentText : Theme.muted; Layout.preferredWidth: 26; wrapMode: Text.NoWrap }
                            Copy { text: chapterRow.start; font.family: Theme.mono; font.pixelSize: Theme.px(12); color: Theme.muted; Layout.preferredWidth: 64; wrapMode: Text.NoWrap }
                            Field {
                                id: titleField
                                // the title as it was when editing began, for Esc
                                property string before: ""
                                property string beforeOrigin: ""
                                quiet: true; text: chapterRow.title; implicitHeight: Theme.compact ? 28 : 32; Layout.leftMargin: -10
                                placeholderText: "Track " + chapterRow.number.toString().padStart(2, "0")
                                font.pixelSize: Theme.px(14); font.weight: Font.Medium; Layout.fillWidth: true; enabled: !win.appView.busy
                                onActiveFocusChanged: if (activeFocus) {
                                    page.selectedChapter = chapterRow.index
                                    before = chapterRow.title
                                    beforeOrigin = chapterRow.origin
                                }
                                onTextEdited: backend.disc.editTitle(chapterRow.index, text)
                                Keys.onReturnPressed: focus = false
                                Keys.onEnterPressed: focus = false
                                Keys.onEscapePressed: {
                                    if (chapterRow.title !== before) backend.disc.restoreTitle(chapterRow.index, before, beforeOrigin)
                                    focus = false
                                }
                                Keys.onUpPressed: page.editTitleAt(chapterRow.index - 1)
                                Keys.onDownPressed: page.editTitleAt(chapterRow.index + 1)
                            }
                            // Music / talk from the loudness outline (shown once the waveform is ready)
                            // Click to set it by hand (a dot marks a hand-set one)
                            Copy {
                                id: kindCell
                                readonly property string kind: (win.discView.chapterKinds || {})[String(chapterRow.number)] || ""
                                readonly property bool manual: page.kindManual.indexOf(chapterRow.number) >= 0
                                visible: page.kindsShown; Layout.preferredWidth: 64; horizontalAlignment: Text.AlignRight; wrapMode: Text.NoWrap
                                text: kind && (kind !== "music" || page.kindMode === "show" || manual) ? win.tr("kind_" + kind) : ""
                                font.pixelSize: Theme.px(12); font.underline: kindHover.hovered && !win.appView.busy
                                color: kindHover.hovered ? Theme.text : manual ? Theme.accentText
                                     : kind === "talk" || kind === "interlude" || kind === "unsure" ? Theme.sub : Theme.faint
                                Rectangle {
                                    visible: kindCell.manual; width: 5; height: 5; radius: 2.5; color: Theme.accent
                                    x: parent.width - parent.contentWidth - 9; anchors.verticalCenter: parent.verticalCenter
                                }
                                HoverHandler { id: kindHover; enabled: !win.appView.busy }
                                // A MouseArea takes the click, so the row does not also react to it
                                MouseArea {
                                    anchors.fill: parent; enabled: !win.appView.busy; cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        kindMenu.row = chapterRow.index; kindMenu.number = chapterRow.number; kindMenu.kind = kindCell.kind
                                        kindMenu.popup()
                                    }
                                }
                                ToolTip.visible: kindHover.hovered; ToolTip.delay: 500
                                ToolTip.text: (kindCell.manual ? win.tr("kindManualTip") + " · " : "") + win.tr("kindSetTip")
                            }
                            Copy { text: chapterRow.duration; font.family: Theme.mono; font.pixelSize: Theme.px(12); color: Theme.sub; Layout.preferredWidth: 52; horizontalAlignment: Text.AlignRight; wrapMode: Text.NoWrap }
                            Copy {
                                visible: page.originsShown
                                text: chapterRow.origin ? win.tr(chapterRow.origin) : ""
                                color: chapterRow.origin === "edited" ? Theme.sub : Theme.faint; font.pixelSize: Theme.px(12)
                                Layout.preferredWidth: 64; horizontalAlignment: Text.AlignRight; wrapMode: Text.NoWrap
                            }
                            IconButton {
                                id: chapterMore
                                iconKind: "more"
                                implicitWidth: 28; implicitHeight: 28; Layout.preferredWidth: 28
                                enabled: !win.appView.busy
                                opacity: !enabled ? 0.25 : chapterHover.hovered || hovered || visualFocus || (chapterMenu.opened && chapterMenu.row === chapterRow.index) ? 1 : 0.35
                                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                                onClicked: page.openChapterMenu(chapterRow.index, chapterRow.seconds, chapterMore, 0, chapterMore.height + 4)
                                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("chapterActions")
                                Accessible.name: win.tr("chapterActions") + " " + chapterRow.number
                            }
                        }
                    }
                }
            }
        }

        Splitter {
            Layout.fillHeight: true; Layout.leftMargin: -6; Layout.rightMargin: -6; z: 1; divider: true
            size: page.rightWidth; direction: -1; minimum: 260; maximum: Math.min(520, page.width - page.leftWidth - page.centerMinimum - 24)
            onResized: function(value) { page.rightLive = value }
            onCommitted: function(value) { backend.setLayoutSize("work_right", value); page.rightLive = -1 }
            onReset: backend.setLayoutSize("work_right", -1)
        }
        // ---------- Right: streams ----------
        Card {
            flat: true
            Layout.preferredWidth: page.rightWidth; Layout.fillHeight: true
            // Every stream stays visible: when the column outgrows the card it scrolls as a whole,
            // instead of the audio list collapsing to nothing.
            Flickable {
                id: streamFlick
                anchors.fill: parent; clip: true
                contentWidth: width; contentHeight: streamColumn.height
                boundsBehavior: Flickable.StopAtBounds; interactive: contentHeight > height
                ScrollBar.vertical: SlimScrollBar { id: streamBar }
            ColumnLayout {
                id: streamColumn
                width: streamFlick.width - streamBar.gutter; height: Math.max(streamFlick.height, implicitHeight); spacing: 18
                RowLayout {
                    Layout.fillWidth: true; Layout.preferredHeight: 28; spacing: 6
                    Item { Layout.fillWidth: true }
                    Segmented {
                        itemHeight: 24
                        options: [{ key: "zh", label: "中文" }, { key: "en", label: "EN" }]
                        current: backend.config.language
                        onPicked: function(key) { backend.setPreference("language", key) }
                    }
                    IconButton { iconKind: "gear"; enabled: !win.appView.working; onClicked: backend.navigate("settings"); ToolTip.visible: hovered; ToolTip.text: win.tr("settings"); Accessible.name: win.tr("settings") }
                    IconButton { id: helpButton; iconKind: "help"; onClicked: win.openHelp(helpButton); ToolTip.visible: hovered; ToolTip.text: win.tr("help"); Accessible.name: win.tr("help") }
                }
                // Video stream (video mode): one line of key parameters, full details on click
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    visible: win.discView.hasVideo && win.discView.outputFormat !== "flac"
                    SectionTitle { text: win.tr("videoTitle"); Layout.fillWidth: true }
                    StreamCard {
                        id: videoCard
                        readonly property var parts: (win.discView.videoSummary || "").split(" · ").filter(function(x) { return x !== "" })
                        Layout.fillWidth: true
                        selectable: false; leadIcon: "film"
                        title: parts.length ? parts[0] : "—"; chips: parts.slice(1); extra: win.discView.videoExtra || ""
                        detailsTip: win.tr("tiShow"); accessibleName: win.discView.videoSummary
                        onToggled: win.showTrackInfo("video", 0)
                        onDetails: win.showTrackInfo("video", 0)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        SectionTitle { text: win.tr("audioTitle"); Layout.fillWidth: true }
                    }
                    ListView {
                        id: audioList
                        Layout.fillWidth: true; Layout.preferredHeight: contentHeight; interactive: false; spacing: 8; model: audioModel
                        populate: ListEnter {}
                        add: ListEnter {}
                        delegate: StreamCard {
                            id: au
                            required property int index
                            required property string label
                            required property bool chosen
                            required property var model
                            width: ListView.view.width
                            title: au.model.title; chips: au.model.chips; extra: au.model.extra
                            tag: au.index === 0 ? win.tr("recommended") : ""
                            checked: au.chosen; interactive: !win.appView.busy
                            detailsTip: win.tr("tiShow"); accessibleName: au.label
                            onToggled: backend.disc.selectAudio(au.index)
                            onDetails: win.showTrackInfo("audio", au.index)
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    visible: win.discView.outputFormat !== "flac"
                    RowLayout {
                        Layout.fillWidth: true
                        SectionTitle { text: win.tr("subtitles"); Layout.fillWidth: true }
                        ActionButton {
                            visible: subList.count > 0
                            readonly property bool allSelected: win.discView.subtitleSelected === subList.count
                            text: win.tr(allSelected ? "selectNone" : "selectAll")
                            implicitHeight: 26; ghost: true; enabled: !win.appView.busy && subList.count > 0
                            onClicked: backend.disc.setAllTracks("subtitle", !allSelected)
                        }
                    }
                    ListView {
                        id: subList
                        Layout.fillWidth: true; Layout.preferredHeight: contentHeight; interactive: false; spacing: 8
                        visible: count > 0; model: subtitleModel
                        delegate: StreamCard {
                            id: sub
                            required property int index
                            required property string label
                            required property bool chosen
                            required property var model
                            width: ListView.view.width
                            title: sub.model.title; chips: sub.model.chips; extra: sub.model.extra
                            checked: sub.chosen; interactive: !win.appView.busy
                            detailsTip: win.tr("tiShow"); accessibleName: sub.label
                            onToggled: backend.disc.selectSubtitle(sub.index)
                            onDetails: win.showTrackInfo("subtitle", sub.index)
                        }
                    }
                    // No subtitle tracks: one plain line, not an empty box
                    Copy { visible: subList.count === 0; text: win.tr("noSubtitles"); color: Theme.faint; Layout.fillWidth: true }
                }
                Item { Layout.fillHeight: true; Layout.fillWidth: true }
                // Metadata summary -> metadata page (audio only: video files carry just their song titles)
                Rectangle {
                    id: metaCard
                    readonly property var meta: win.metaView.meta || ({ album: {}, cover: "" })
                    visible: win.discView.outputFormat === "flac"
                    Layout.fillWidth: true; Layout.preferredHeight: 64; radius: 10
                    color: metaHover.hovered ? Qt.lighter(Theme.raised, Theme.light ? 0.98 : 1.1) : Theme.raised
                    border.color: Theme.line2
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    HoverHandler { id: metaHover }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 6; color: Theme.chip; clip: true
                            Image {
                                id: metaThumb; anchors.fill: parent; fillMode: Image.PreserveAspectCrop; asynchronous: true; cache: false
                                sourceSize.width: 88
                                source: metaCard.meta.cover ? "file:///" + String(metaCard.meta.cover).replace(/\\/g, "/") : ""
                            }
                            Icon { anchors.centerIn: parent; width: 20; height: 20; kind: "disc"; ink: Theme.faint; visible: metaThumb.status !== Image.Ready }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Copy { text: win.tr("metadata"); font.weight: Font.DemiBold; wrapMode: Text.NoWrap }
                            Copy {
                                text: [metaCard.meta.album.artist, metaCard.meta.album.album, metaCard.meta.album.date].filter(function(x) { return x }).join(" · ") || win.tr("metaNotSet")
                                color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                            }
                        }
                        Copy { text: win.tr("metaEdit"); color: Theme.accentText; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; enabled: !win.appView.working; onClicked: backend.navigate("metadata") }
                }
                // Export estimate: what the current selection will produce, and whether it fits
                Rectangle {
                    id: estCard
                    readonly property var est: win.discView.exportEstimate || ({})
                    Layout.fillWidth: true; Layout.preferredHeight: estInfo.implicitHeight + 22; radius: 10
                    color: Theme.raised; border.color: est.enough === false ? Theme.dangerLine : Theme.line2
                    ColumnLayout {
                        id: estInfo; x: 12; y: 11; width: parent.width - 24; spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Copy { text: win.tr("estimateTitle"); font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.NoWrap }
                            Copy {
                                visible: estCard.est.files > 0
                                text: estCard.est.size ? win.fmt("estimateSize", { s: estCard.est.size }) : win.tr("estimateUnknown")
                                font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
                                color: estCard.est.size ? Theme.text : Theme.faint
                            }
                        }
                        Copy {
                            text: estCard.est.files > 0 ? (estCard.est.duration ? win.fmt("estimateFiles", { n: estCard.est.files, d: estCard.est.duration }) : win.fmt("estimateFilesOnly", { n: estCard.est.files })) : win.tr("estimateNone")
                            color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                        }
                        RowLayout {
                            visible: estCard.est.free !== undefined && estCard.est.free !== ""
                            Layout.fillWidth: true; spacing: 6
                            Rectangle {
                                Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4
                                color: estCard.est.enough === false ? Theme.danger : estCard.est.enough ? Theme.good : Theme.faint
                            }
                            Copy {
                                text: win.fmt("estimateFree", { d: estCard.est.drive, f: estCard.est.free })
                                      + (estCard.est.enough === false ? " · " + win.tr("estimateTight") : "")
                                color: estCard.est.enough === false ? Theme.danger : Theme.muted
                                font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                            }
                        }
                        // Where the files go (the album folder inside the chosen output folder)
                        RowLayout {
                            Layout.fillWidth: true; Layout.topMargin: 2; spacing: 6
                            Icon { kind: "folder"; ink: Theme.faint; Layout.preferredWidth: 13; Layout.preferredHeight: 13 }
                            Copy {
                                text: estCard.est.folder || win.discView.output || win.tr("chooseFolder")
                                font.family: Theme.mono; font.pixelSize: Theme.px(11)
                                color: estCard.est.folder || win.discView.output ? Theme.faint : Theme.pendingText
                                Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideMiddle
                                HoverHandler { id: folderHover }
                                ToolTip.visible: folderHover.hovered && truncated; ToolTip.delay: 400; ToolTip.text: text
                            }
                            Copy {
                                text: win.tr("change"); color: win.appView.working ? Theme.faint : Theme.accentText
                                font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
                                MouseArea {
                                    anchors.fill: parent; anchors.margins: -4; enabled: !win.appView.working
                                    cursorShape: Qt.PointingHandCursor; onClicked: win.openFolder("output")
                                }
                                Accessible.role: Accessible.Button; Accessible.name: win.tr("output")
                            }
                        }
                    }
                }
                // What will be exported, and the button that starts it
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    Copy {
                        text: win.discView.outputFormat === "flac"
                            ? win.fmt("flacExportSummary", { n: win.discView.chapterSelected, a: win.discView.audioSelected })
                            : win.fmt("exportSummary", { n: win.discView.chapterSelected, a: win.discView.audioSelected, s: win.discView.subtitleSelected })
                              + (win.discView.keepVideo ? "" : " · " + win.tr("videoExcluded"))
                        color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.NoWrap; elide: Text.ElideRight
                    }
                    ActionButton {
                        text: win.tr("extract"); primary: true; large: true; Layout.fillWidth: true
                        enabled: !win.appView.working && win.discView.chapterSelected > 0 && win.discView.audioSelected > 0
                        onClicked: backend.exporter.startExport()
                    }
                }
            }
            }
        }
    }
}
