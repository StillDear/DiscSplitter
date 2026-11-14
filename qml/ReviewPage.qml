import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
ColumnLayout {
    id: reviewPage
    required property var win
    spacing: 0
    // Panel widths: dragged live (…Live), otherwise the saved layout, otherwise the default.
    readonly property var layoutSizes: backend.config.layout || ({})
    readonly property int centerMinimum: 420
    // A saved width never squeezes the middle panel when the window is narrower than when it was set.
    function fit(value, share) { return Math.max(200, Math.min(value, (win.width - 24) * share)) }
    property real rightLive: -1
    readonly property real rightWidth: rightLive > 0 ? rightLive : fit(layoutSizes.review_right || 380, 0.5)
    // Music / talk per chapter is known once the disc's loudness outline is ready
    readonly property bool kindsKnown: Object.keys(win.discView.chapterKinds || {}).length > 0
    readonly property int talkLeft: (win.namesView.reviewCounts || {}).talk || 0
    // Reads the settings it depends on, so the preview follows them
    function fileName(number, title) {
        void win.discView.outputFormat; void backend.config.filename_template
        return backend.names.fileNamePreview(number, title)
    }
    component HeadText: Copy { color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; elide: Text.ElideRight }
    // One surface filling the window (no title bar or footer): the table on the left, the title
    // source with the page's own controls on the right, divided by a hairline.
    RowLayout {
        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0

        // ---------- Review table ----------
        Card {
            flat: true; clip: true
            // Width comes from what the right column leaves, never from the header's buttons.
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 0; Layout.minimumWidth: 0; padding: 20
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                RowLayout {
                    Layout.fillWidth: true; spacing: 10
                    IconButton {
                        visible: !win.appView.pipeline; iconKind: "back"; implicitWidth: 32; implicitHeight: 32
                        enabled: !win.appView.busy; Layout.leftMargin: -6
                        onClicked: backend.navigate(win.discView.album || win.discView.source ? "main" : "start")
                        ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("back"); Accessible.name: win.tr("back")
                    }
                    Copy { text: win.tr("review"); font.pixelSize: Theme.px(20); font.bold: true; wrapMode: Text.NoWrap }
                    Badge {
                        tone: "accent"; visible: win.namesView.mbRelease !== "" && win.namesView.reviewSource === "online"
                        text: win.fmt("mbFrom", { name: win.namesView.mbRelease })
                        // Gives way first when the header runs out of room
                        Layout.fillWidth: true; Layout.minimumWidth: 40; Layout.maximumWidth: Math.min(360, implicitWidth); clip: true
                    }
                    Item { Layout.fillWidth: true }
                    Segmented {
                        visible: win.namesView.reviewCanAlign && reviewList.count > 0 && !reviewList.waiting; enabled: !win.appView.busy
                        options: [{ key: "duration", label: win.tr("alignDuration") }, { key: "order", label: win.tr("alignOrder") }]
                        current: win.namesView.reviewMode
                        onPicked: function(key) { backend.names.realignReview(key) }
                    }
                    ActionButton {
                        ghost: true; text: win.tr("stripBrackets")
                        visible: win.namesView.reviewStrippable && reviewList.count > 0 && !reviewList.waiting
                        enabled: !win.appView.busy
                        onClicked: backend.names.stripReviewBrackets()
                        ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("stripBracketsHint")
                    }
                    ActionButton { ghost: true; text: win.tr("selectAll"); visible: reviewList.count > 0 && !reviewList.waiting; onClicked: backend.names.checkAllReview(true) }
                    ActionButton { ghost: true; text: win.tr("selectNone"); visible: reviewList.count > 0 && !reviewList.waiting; onClicked: backend.names.checkAllReview(false) }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: hintText.implicitHeight + 18; radius: 10; color: Theme.raised
                    Copy {
                        id: hintText; anchors.fill: parent; anchors.margins: 9; anchors.leftMargin: 12
                        text: reviewList.waiting ? reviewList.pickText
                            : win.tr(win.namesView.reviewMode === "chapter" ? "reviewHintChapter"
                                     : win.namesView.reviewCanAlign && win.namesView.reviewMode === "duration" ? "reviewHintAlign" : "reviewHint")
                              + (backend.config.language === "zh" ? "" : " ") + win.tr("reviewEditHint")
                        color: Theme.sub; font.pixelSize: Theme.px(12)
                    }
                }
                // Filter by state, and take non-song chapters out of naming
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    visible: reviewList.count > 0
                    Segmented {
                        id: reviewFilter
                        property string value: "all"
                        readonly property var counts: win.namesView.reviewCounts || ({})
                        itemHeight: 26
                        options: [{ key: "all", label: win.fmt("reviewFilterAll", { n: counts.all || 0 }) }]
                            .concat(reviewList.waiting ? [] : [
                                { key: "matched", label: win.fmt("reviewFilterMatched", { n: counts.matched || 0 }) },
                                { key: "check", label: win.fmt("reviewFilterCheck", { n: counts.check || 0 }) },
                                { key: "unmatched", label: win.fmt("reviewFilterUnmatched", { n: counts.unmatched || 0 }) }])
                            .concat((counts.removed || 0) > 0 ? [{ key: "removed", label: win.fmt("reviewFilterRemoved", { n: counts.removed }) }] : [])
                        current: options.some(function(o) { return o.key === value }) ? value : "all"
                        onPicked: function(key) { value = key; reviewList.positionViewAtBeginning() }
                    }
                    Item { Layout.fillWidth: true }
                    ActionButton {
                        ghost: true; implicitHeight: 28
                        visible: reviewPage.talkLeft > 0
                        text: win.tr("reviewRemoveTalk") + " (" + reviewPage.talkLeft + ")"
                        enabled: !win.appView.busy
                        onClicked: backend.names.removeNonSongs()
                        ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("reviewRemoveTalkHint")
                    }
                    ActionButton {
                        ghost: true; implicitHeight: 28
                        visible: win.namesView.reviewRemoved > 0
                        text: win.fmt("reviewRestoreAll", { n: win.namesView.reviewRemoved })
                        enabled: !win.appView.busy
                        onClicked: backend.names.restoreRemoved()
                    }
                }
                // Column heads, in two groups: this disc | the candidate
                Item {
                    Layout.fillWidth: true; Layout.preferredHeight: heads.implicitHeight + 8
                    RowLayout {
                        id: heads
                        x: 12; width: parent.width - 24 - reviewBar.gutter; spacing: 0
                        ColumnLayout {
                            Layout.preferredWidth: reviewList.leftWidth; Layout.maximumWidth: reviewList.leftWidth; spacing: 4
                            Copy { text: win.tr("groupDisc"); font.pixelSize: Theme.px(12); font.weight: Font.DemiBold; color: Theme.sub; wrapMode: Text.NoWrap; Layout.leftMargin: 28 }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Item { Layout.preferredWidth: 18 }
                                Item { Layout.preferredWidth: 24 }
                                HeadText { text: "#"; Layout.preferredWidth: 22 }
                                HeadText { text: win.tr("duration"); Layout.preferredWidth: 46 }
                                HeadText {
                                    text: win.tr("kindColumn") + "*"; Layout.preferredWidth: 56; visible: reviewPage.kindsKnown
                                    HoverHandler { id: reviewKindHover }
                                    ToolTip.visible: reviewKindHover.hovered; ToolTip.delay: 200; ToolTip.text: win.tr("kindHint")
                                }
                                HeadText { text: win.tr("current"); Layout.fillWidth: true }
                            }
                        }
                        Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.line2 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Copy { text: win.tr("groupCandidate"); font.pixelSize: Theme.px(12); font.weight: Font.DemiBold; color: Theme.sub; wrapMode: Text.NoWrap; Layout.leftMargin: 12 }
                            RowLayout {
                                Layout.fillWidth: true; Layout.leftMargin: 12; spacing: 8
                                HeadText { text: win.tr("proposed"); Layout.fillWidth: true }
                                HeadText { text: win.tr("sourceTrack"); Layout.preferredWidth: reviewList.sourceWidth }
                                HeadText { text: win.tr("status"); Layout.preferredWidth: 76 }
                                Item { Layout.preferredWidth: 26 }
                            }
                        }
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line2 }
                }
                ListView {
                    id: reviewList
                    // Chapters listed while no release / list has been chosen yet (rows are "waiting").
                    readonly property bool waiting: win.namesView.reviewCount === 0
                    readonly property string pickText: win.namesView.reviewSource === "paste" || win.namesView.reviewSource === "import" ? win.tr("listPick")
                        : win.namesView.mb === "loading" ? win.tr("mbLoading") : win.tr("mbPick")
                    // Shared column geometry for the heads and every row
                    readonly property real rowWidth: width - reviewBar.gutter - 24
                    readonly property real leftWidth: Math.round(Math.max(260, rowWidth * 0.4))
                    readonly property real sourceWidth: 150
                    property int shown: 0          // rows the filter lets through (for the empty message)
                    function passes(confidence) {
                        const f = reviewFilter.current
                        if (f === "all") return true
                        if (f === "matched") return confidence === "matched" || confidence === "manual"
                        if (f === "removed") return confidence === "removed"
                        if (f === "unmatched") return confidence === "no_match"
                        return confidence !== "matched" && confidence !== "manual" && confidence !== "removed"
                               && confidence !== "no_match" && confidence !== "waiting"
                    }
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 0; model: reviewModel
                    Copy {
                        anchors.centerIn: parent; width: Math.min(parent.width - 40, 420)
                        visible: reviewList.count === 0 || reviewList.contentHeight < 1; horizontalAlignment: Text.AlignHCenter
                        text: reviewList.count === 0 ? reviewList.pickText : win.tr("reviewFilterEmpty")
                        color: Theme.muted; lineHeight: 1.3
                    }
                    ScrollBar.vertical: SlimScrollBar { id: reviewBar }
                    populate: ListEnter {}
                    delegate: Rectangle {
                        id: reviewRow
                        required property int index
                        required property int number
                        required property string current
                        required property string proposed
                        required property string duration
                        required property string confidence
                        required property string detail
                        required property bool checked
                        required property int entry
                        required property string entryLabel
                        required property string entryDuration
                        required property real entrySeconds
                        required property real seconds
                        required property string kind
                        readonly property bool removed: confidence === "removed"
                        readonly property bool shownByFilter: reviewList.passes(confidence)
                        readonly property bool hearing: win.previewView.previewRow === number - 1 && win.previewView.previewUrl !== ""
                        readonly property real diff: entry >= 0 && entrySeconds > 0 && seconds > 0 ? entrySeconds - seconds : NaN
                        readonly property real tolerance: win.namesView.reviewTolerance || 20
                        width: ListView.view.width - reviewBar.gutter
                        height: shownByFilter ? Theme.rowHeight + 14 : 0
                        visible: shownByFilter
                        color: rowHover.hovered ? Theme.raised : "transparent"
                        HoverHandler { id: rowHover }
                        // Rows are divided by a hairline
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line2 }
                        RowLayout {
                            x: 12; width: reviewList.rowWidth; height: parent.height - 1; spacing: 0
                            // ---- this disc
                            RowLayout {
                                Layout.preferredWidth: reviewList.leftWidth; Layout.maximumWidth: reviewList.leftWidth; spacing: 8
                                opacity: reviewRow.removed ? 0.5 : 1
                                SelectionMark {
                                    checked: reviewRow.checked
                                    opacity: reviewRow.removed || (reviewRow.confidence === "waiting" && !reviewRow.proposed) ? 0.35 : 1
                                    MouseArea {
                                        anchors.fill: parent; anchors.margins: -8; cursorShape: Qt.PointingHandCursor
                                        enabled: !reviewRow.removed && (reviewRow.confidence !== "waiting" || reviewRow.proposed !== "")
                                        onClicked: backend.names.checkReview(reviewRow.index, !reviewRow.checked)
                                    }
                                }
                                IconButton {
                                    iconKind: reviewRow.hearing && win.previewPlaying ? "pause" : "play"
                                    implicitWidth: 24; implicitHeight: 24
                                    ink: reviewRow.hearing ? Theme.accent : Theme.muted
                                    opacity: reviewRow.hearing || rowHover.hovered || hovered ? 1 : 0.35
                                    enabled: !win.appView.busy
                                    onClicked: reviewRow.hearing ? win.togglePreview() : backend.preview.listenChapter(reviewRow.number - 1)
                                    ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("reviewListen")
                                    Accessible.name: win.tr("reviewListen") + " " + reviewRow.number
                                }
                                Copy {
                                    text: reviewRow.number.toString().padStart(2, "0"); Layout.preferredWidth: 22; font.family: Theme.mono
                                    color: reviewRow.hearing ? Theme.accentText : Theme.muted; wrapMode: Text.NoWrap
                                }
                                Copy { text: reviewRow.duration; Layout.preferredWidth: 46; font.family: Theme.mono; font.pixelSize: Theme.px(12); color: Theme.muted; wrapMode: Text.NoWrap }
                                Copy {
                                    visible: reviewPage.kindsKnown; Layout.preferredWidth: 56; wrapMode: Text.NoWrap; elide: Text.ElideRight
                                    text: reviewRow.kind ? win.tr("kind_" + reviewRow.kind) : ""
                                    font.pixelSize: Theme.px(12)
                                    color: reviewRow.kind === "talk" || reviewRow.kind === "interlude" ? Theme.pendingText
                                         : reviewRow.kind === "unsure" ? Theme.sub : Theme.faint
                                }
                                Copy {
                                    text: reviewRow.current || "—"; color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                                }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.line2 }
                            // ---- the candidate
                            RowLayout {
                                Layout.fillWidth: true; Layout.leftMargin: 12; spacing: 8
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 0
                                    opacity: reviewRow.removed ? 0.5 : 1
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 2
                                        Field {
                                            quiet: true; text: reviewRow.proposed; implicitHeight: 28; Layout.leftMargin: -10
                                            font.pixelSize: Theme.px(14); font.weight: Font.Medium; Layout.fillWidth: true
                                            placeholderText: "—"; enabled: !reviewRow.removed
                                            onTextEdited: backend.names.editReview(reviewRow.index, text)
                                        }
                                        IconButton {
                                            id: pickButton
                                            iconKind: "down"; implicitWidth: 26; implicitHeight: 26
                                            visible: win.namesView.reviewPool.length > 0 && !reviewRow.removed; enabled: !win.appView.busy
                                            ToolTip.visible: hovered; ToolTip.text: win.tr("pickTrack")
                                            onClicked: trackPicker.openFor(reviewRow.index, reviewRow.entry, pickButton)
                                        }
                                    }
                                    // The file it will be exported as
                                    Copy {
                                        readonly property string file: reviewRow.removed || !reviewRow.proposed.trim() ? ""
                                            : reviewPage.fileName(reviewRow.number, reviewRow.proposed)
                                        visible: file !== ""; text: "→ " + file
                                        font.family: Theme.mono; font.pixelSize: Theme.px(11); color: Theme.faint
                                        Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideMiddle
                                        HoverHandler { id: fileHover }
                                        ToolTip.visible: fileHover.hovered; ToolTip.delay: 400; ToolTip.text: win.fmt("reviewFileTip", { f: file })
                                    }
                                }
                                // Source track, and how far its length is from the chapter's
                                ColumnLayout {
                                    Layout.preferredWidth: reviewList.sourceWidth; spacing: 2
                                    opacity: reviewRow.removed ? 0.5 : 1
                                    Copy {
                                        Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                                        font.family: Theme.mono; font.pixelSize: Theme.px(12)
                                        text: reviewRow.entry >= 0 ? "#" + reviewRow.entryLabel + (reviewRow.entryDuration ? " · " + reviewRow.entryDuration : "") : "—"
                                        color: reviewRow.entry >= 0 ? Theme.sub : Theme.faint
                                    }
                                    Copy {
                                        visible: !isNaN(reviewRow.diff)
                                        readonly property real gap: Math.abs(reviewRow.diff)
                                        text: win.tr("reviewDiff") + " " + (reviewRow.diff >= 0 ? "+" : "−")
                                              + (gap < 60 ? Math.round(gap) + "s" : Math.floor(gap / 60) + ":" + String(Math.round(gap % 60)).padStart(2, "0"))
                                        font.family: Theme.mono; font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap
                                        color: gap <= reviewRow.tolerance ? Theme.faint : gap <= reviewRow.tolerance * 3 ? Theme.pendingText : Theme.danger
                                    }
                                }
                                Copy {
                                    text: reviewRow.confidence === "waiting" ? "" : win.tr(reviewRow.confidence); Layout.preferredWidth: 76
                                    font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; elide: Text.ElideRight
                                    color: reviewRow.removed ? Theme.faint
                                         : reviewRow.confidence === "matched" || reviewRow.confidence === "manual" ? Theme.goodText : Theme.pendingText
                                    ToolTip.visible: reviewHover.hovered && reviewRow.detail !== ""; ToolTip.text: reviewRow.detail
                                    HoverHandler { id: reviewHover }
                                }
                                // Take the chapter out of naming / put it back
                                IconButton {
                                    iconKind: reviewRow.removed ? "refresh" : "close"; implicitWidth: 26; implicitHeight: 26
                                    enabled: !win.appView.busy
                                    opacity: reviewRow.removed || rowHover.hovered || hovered ? 1 : 0.25
                                    onClicked: backend.names.removeChapter(reviewRow.number, !reviewRow.removed)
                                    ToolTip.visible: hovered; ToolTip.delay: 300
                                    ToolTip.text: win.tr(reviewRow.removed ? "reviewRestore" : "reviewRemove")
                                    Accessible.name: win.tr(reviewRow.removed ? "reviewRestore" : "reviewRemove") + " " + reviewRow.number
                                }
                            }
                        }
                    }
                }
            }
        }

        Splitter {
            Layout.fillHeight: true; Layout.leftMargin: -6; Layout.rightMargin: -6; z: 1; divider: true
            size: reviewPage.rightWidth; direction: -1; minimum: 300; maximum: Math.min(620, reviewPage.width - reviewPage.centerMinimum - 12)
            onResized: function(value) { reviewPage.rightLive = value }
            onCommitted: function(value) { backend.setLayoutSize("review_right", value); reviewPage.rightLive = -1 }
            onReset: backend.setLayoutSize("review_right", -1)
        }
        // ---------- Title source: tabs, then that source's panel ----------
        Card {
            flat: true; padding: 20
            Layout.preferredWidth: reviewPage.rightWidth; Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent; spacing: 16
                // Work in progress (what the title bar used to show)
                RowLayout {
                    visible: win.appView.busy && !win.appView.pipeline
                    Layout.fillWidth: true; spacing: 6
                    BusyIndicator { running: win.appView.busy && !win.appView.pipeline; visible: running; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                    Copy {
                        visible: win.appView.busy && !win.appView.pipeline; text: win.tr(win.appView.status)
                        color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; elide: Text.ElideRight; Layout.fillWidth: true
                    }
                }
                // The source panel takes what room is left; on a short window it is cut off at the
                // bottom rather than pushing the apply buttons out of sight.
                Item {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                ColumnLayout {
                    anchors.fill: parent; spacing: 16
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    SectionTitle { text: win.tr("titleSource"); Layout.fillWidth: true }
                    Segmented {
                        fill: true; Layout.fillWidth: true; enabled: !win.appView.busy
                        options: [{ key: "disc", label: win.tr("fromDisc") }, { key: "online", label: win.tr("online") },
                                  { key: "paste", label: win.tr("paste") }]
                        current: win.namesView.reviewSource
                        onPicked: function(key) {
                            if (key === "disc") backend.names.reviewEmbedded()
                            else if (key === "paste") win.pasteTracklist()
                            else if (win.namesView.reviewSource !== "online") backend.names.openOnline()
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

                // Disc / paste / import: say what was loaded, offer to redo it or go online.
                ColumnLayout {
                    visible: win.namesView.reviewSource !== "online"
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: srcInfo.implicitHeight + 28; radius: 10
                        color: Theme.raised; border.color: Theme.line2
                        ColumnLayout {
                            id: srcInfo; x: 14; y: 14; width: parent.width - 28; spacing: 6
                            Copy {
                                text: win.namesView.reviewSource === "disc" ? win.tr("srcDiscTitle")
                                    : win.namesView.reviewCount === 0 ? win.tr(win.namesView.reviewSource === "paste" ? "srcEmptyPaste" : "srcEmptyImport")
                                    : win.namesView.reviewSource === "paste" ? win.tr("srcPasteTitle") : win.namesView.reviewSourceName
                                font.pixelSize: Theme.px(15); font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere
                            }
                            Copy {
                                visible: win.namesView.reviewCount > 0
                                text: win.fmt("srcCount", { n: win.namesView.reviewCount, c: reviewList.count })
                                color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true
                            }
                        }
                    }
                    Copy {
                        text: win.namesView.reviewSource === "disc" ? win.tr("srcDiscHint") : win.namesView.reviewCount === 0 ? win.tr("srcEmptyHint") : win.tr("srcListHint")
                        color: Theme.sub; font.pixelSize: Theme.px(12); Layout.fillWidth: true; lineHeight: 1.35
                    }
                    ActionButton {
                        text: win.namesView.reviewSource === "disc" ? win.tr("reloadDisc")
                            : win.namesView.reviewSource === "paste" ? win.tr(win.namesView.reviewCount === 0 ? "paste" : "repaste")
                            : win.tr(win.namesView.reviewCount === 0 ? "chooseFile" : "otherFile")
                        primary: win.namesView.reviewSource !== "disc" && win.namesView.reviewCount === 0
                        Layout.fillWidth: true; enabled: !win.appView.busy
                        onClicked: {
                            if (win.namesView.reviewSource === "disc") backend.names.reviewEmbedded()
                            else if (win.namesView.reviewSource === "paste") win.pasteTracklist()
                            else win.importTracklist()
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Copy { text: win.tr("tryOnline"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true }
                    ActionButton { text: win.tr("online"); primary: win.namesView.reviewSource === "disc" || win.namesView.reviewCount > 0; Layout.fillWidth: true; enabled: !win.appView.busy; onClicked: backend.names.openOnline() }
                }

                // Online lookup
                ColumnLayout {
                    visible: win.namesView.reviewSource === "online"
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 10
                    id: queryForm
                    // Follow the backend's query (new disc, or a search run on entry) without fighting the user's typing.
                    property string artistValue: win.namesView.mbArtist
                    property string albumValue: win.namesView.mbAlbum
                    onArtistValueChanged: if (artist.text !== artistValue) artist.text = artistValue
                    onAlbumValueChanged: if (album.text !== albumValue) album.text = albumValue
                    // The barcode field stays folded away until asked for (or already filled in).
                    function run() { if (!win.appView.busy) backend.names.search(artist.text, album.text, barcodeToggle.open ? barcode.text : "") }
                    // Labels in front of their fields, in one column so the fields line up
                    GridLayout {
                        Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 10
                        Copy { text: win.tr("sourceLabel"); color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                        SourcePicker {
                            Layout.fillWidth: true; enabled: !win.appView.busy
                            current: win.namesView.titleSource || "musicbrainz"
                            onPicked: function(key) { backend.names.setTitleSource(key) }
                        }
                        Copy { text: win.tr("artist"); color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                        Field { id: artist; text: win.namesView.mbArtist; Layout.fillWidth: true; onAccepted: queryForm.run(); Accessible.name: win.tr("artist") }
                        Copy { text: win.tr("album"); color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                        Field { id: album; text: win.namesView.mbAlbum; Layout.fillWidth: true; onAccepted: queryForm.run(); Accessible.name: win.tr("album") }
                        Disclosure {
                            id: barcodeToggle; Layout.columnSpan: 2
                            text: win.tr("barcodeToggle"); enabled: !win.appView.busy
                            onOpenChanged: if (open) barcode.forceActiveFocus()
                        }
                        Copy { visible: barcodeToggle.open; text: win.tr("barcodeShort"); color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                        Field { id: barcode; visible: barcodeToggle.open; mono: true; Layout.fillWidth: true; placeholderText: win.tr("barcodePlaceholder"); onAccepted: queryForm.run(); Accessible.name: win.tr("barcode") }
                    }
                    ActionButton {
                        text: win.namesView.mb === "searching" ? win.tr("sourceSearching") : win.tr("searchSource")
                        primary: releaseList.count === 0; Layout.fillWidth: true; enabled: !win.appView.busy; onClicked: queryForm.run()
                    }
                }
                SectionTitle { text: win.tr("versions"); note: releaseList.count > 0 ? String(releaseList.count) : ""; Layout.fillWidth: true }
                Rectangle {
                    readonly property string message: win.namesView.mb === "searching" ? win.tr("sourceSearching")
                        : win.namesView.mb === "empty" ? win.tr("mbEmpty")
                        : win.namesView.mb === "error" ? win.namesView.mbError
                        : win.namesView.mb === "idle" && releaseList.count === 0 ? win.tr("mbIdle") : ""
                    visible: message !== ""
                    Layout.fillWidth: true; Layout.preferredHeight: statusText.implicitHeight + 18; radius: 10
                    color: win.namesView.mb === "error" ? "transparent" : Theme.raised
                    border.color: win.namesView.mb === "error" ? Theme.dangerLine : "transparent"
                    Copy {
                        id: statusText; anchors.fill: parent; anchors.margins: 9; anchors.leftMargin: 12
                        text: parent.message; font.pixelSize: Theme.px(12); lineHeight: 1.3
                        color: win.namesView.mb === "error" ? Theme.danger : Theme.sub
                    }
                }
                ListView {
                    id: releaseList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 8; model: releaseModel
                    ScrollBar.vertical: SlimScrollBar { id: releaseBar }
                    populate: ListEnter {}
                    add: ListEnter {}
                    delegate: Rectangle {
                        id: rel
                        required property int index
                        required property string label
                        required property string detail
                        required property int tracks
                        required property int chapters
                        required property string fit
                        required property bool chosen
                        required property string thumb
                        width: ListView.view.width - releaseBar.gutter; height: Math.max(relInfo.implicitHeight, rel.thumb ? 48 : 0) + 22
                        color: rel.chosen ? Theme.accentSoft : relHover.hovered ? Theme.field : Theme.raised; radius: 10
                        border.width: rel.chosen ? 2 : 1
                        border.color: rel.chosen ? Theme.accent : relHover.hovered ? Theme.accent : Theme.line2
                        HoverHandler { id: relHover }
                        Rectangle {
                            id: relThumb
                            visible: rel.thumb !== ""; x: 12; y: 11; width: 48; height: 48; radius: 6; color: Theme.chip; clip: true
                            Image { anchors.fill: parent; source: rel.thumb; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 96 }
                        }
                        ColumnLayout {
                            id: relInfo; x: rel.thumb ? 70 : 12; y: 11; width: parent.width - x - 12; spacing: 6
                            Copy { text: rel.label; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Badge {
                                    tone: rel.fit === "exact" ? "good" : "neutral"
                                    text: rel.fit === "unknown" ? win.tr("mbTracksUnknown") : win.fmt("mbTracks", { n: rel.tracks, c: rel.chapters })
                                }
                                Copy { text: rel.detail; color: Theme.muted; Layout.fillWidth: true; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; elide: Text.ElideRight }
                            }
                        }
                        MouseArea { anchors.fill: parent; enabled: !win.appView.busy; cursorShape: Qt.PointingHandCursor; onClicked: backend.names.selectRelease(rel.index) }
                    }
                }
                Copy { text: win.tr("mbHint"); color: Theme.faint; font.pixelSize: Theme.px(12); Layout.fillWidth: true; lineHeight: 1.3; visible: releaseList.count > 0 }
                }
                }
                }
                // What the footer held: apply the ticked titles, or leave
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 8
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line; Layout.bottomMargin: 4 }
                    Copy { text: win.tr("reviewFooter"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        ActionButton { text: win.tr("cancel"); large: true; onClicked: backend.navigate("main") }
                        ActionButton {
                            Layout.fillWidth: true
                            text: win.namesView.reviewChecked > 0 ? win.fmt("applyN", { n: win.namesView.reviewChecked }) : win.tr("apply")
                            primary: true; large: true; enabled: !win.appView.busy && win.namesView.reviewChecked > 0; onClicked: backend.names.applyReview()
                        }
                    }
                }
            }
        }
    }

    // ---------- Track picker: assign any source track to a chapter ----------
    Popup {
        id: trackPicker
        property int row: -1
        property int current: -1
        function openFor(row, current, anchorItem) {
            trackPicker.row = row; trackPicker.current = current
            const p = anchorItem.mapToItem(reviewPage, 0, anchorItem.height)
            trackPicker.x = Math.max(0, Math.min(p.x - width + anchorItem.width, reviewPage.width - width))
            trackPicker.y = Math.min(p.y + 4, reviewPage.height - height)
            open()
            pickList.positionViewAtIndex(Math.max(0, current + 1), ListView.Center)
        }
        width: 460; height: Math.min(440, reviewPage.height - 40); padding: 8
        modal: false; focus: true; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }
        background: Rectangle { color: Theme.panel; radius: 12; border.color: Theme.line2 }
        ColumnLayout {
            anchors.fill: parent; spacing: 6
            Copy { text: win.tr("pickTrack"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.leftMargin: 8; Layout.topMargin: 4 }
            ListView {
                id: pickList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 1
                model: [{ index: -1, number: "", name: win.tr("noTrack"), duration: "", used: false }].concat(win.namesView.reviewPool || [])
                ScrollBar.vertical: SlimScrollBar { id: pickBar }
                delegate: Rectangle {
                    id: pick
                    required property var modelData
                    readonly property bool on: modelData.index === trackPicker.current
                    width: ListView.view.width - pickBar.gutter; height: Theme.rowHeight - 6; radius: 6
                    color: on ? Theme.accentSoft : pickArea.containsMouse ? Theme.raised : "transparent"
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 10
                        Copy { text: pick.modelData.number; font.family: Theme.mono; color: Theme.muted; Layout.preferredWidth: 22; wrapMode: Text.NoWrap }
                        Copy {
                            text: pick.modelData.name; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                            color: pick.modelData.index < 0 ? Theme.muted : pick.modelData.used && !pick.on ? Theme.faint : Theme.text
                        }
                        Copy { visible: pick.modelData.used && !pick.on; text: win.tr("usedElsewhere"); font.pixelSize: Theme.px(11); color: Theme.faint; wrapMode: Text.NoWrap }
                        Copy { text: pick.modelData.duration; font.family: Theme.mono; font.pixelSize: Theme.px(12); color: Theme.muted; wrapMode: Text.NoWrap }
                    }
                    MouseArea {
                        id: pickArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: { backend.names.assignReview(trackPicker.row, pick.modelData.index); trackPicker.close() }
                    }
                }
            }
        }
    }
}
