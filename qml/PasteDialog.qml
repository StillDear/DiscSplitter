import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
// Paste a set list (text, a screenshot or a web address) on the left; on the right, what each line
// becomes, updated while typing. Lines can be re-typed by hand from there.
Popup {
    id: dialog
    required property var win
    readonly property var pv: win.namesView.pastePreview
    readonly property var ocrState: win.namesView.pasteOcr
    readonly property var web: win.namesView.pasteWeb
    property int disc: 0                 // 0: guess from the disc image name
    property int start: 1
    property int end: 0                  // last chapter the list fills (0: the last one)
    property string mode: "auto"         // "auto" (by duration when possible) | "order"
    property string skipMode: "auto"     // non-song chapters: "auto" (guessed; the default) | "none" (every chapter takes a song) | "lines" (MC lines)
    property var chapterChoices: ({})    // chapter number -> "skip" | "use", set by clicking the chapter strip
    property bool halfwidth: false
    property bool suffixes: false
    property bool original: false
    property int column: -1              // title column of a pasted table (-1: guess)
    property var overrides: ({})         // line key -> "song" | "extra" | "off" | "merged"
    property var excluded: ({})          // line key -> true: unticked, its chapter keeps its current name
    property string lastOcr: ""          // text the last screenshot added (replaced when read again)
    property int webChoice: 0
    property bool shotShown: false
    property bool listenedHere: false    // a chapter was played from the strip (stopped when the dialog closes)
    function clock(ms) {
        const t = Math.max(0, Math.floor(ms / 1000))
        return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0")
    }
    function listen(c) {
        if (listenedHere && win.previewView.previewRow === c.row && !win.previewView.previewLoading) { win.togglePreview(); return }
        listenedHere = true
        backend.preview.listenChapter(c.row)
    }
    onClosed: if (listenedHere) { backend.preview.stopPreview(); listenedHere = false }

    parent: win.contentItem
    anchors.centerIn: parent
    width: Math.min(1480, parent.width - 48)
    height: Math.min(800, parent.height - 48)
    padding: 24; modal: true; focus: true
    closePolicy: Popup.CloseOnEscape
    background: Rectangle { color: Theme.panel; radius: 14; border.color: Theme.line2 }
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, Theme.light ? 0.25 : 0.5) }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: Theme.animate ? 0.96 : 1; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

    function options() {
        return { disc: disc, start: start, end: end, mode: mode, skip: skipMode, chapters: chapterChoices, halfwidth: halfwidth, suffixes: suffixes,
                 original: original, column: column, overrides: overrides, excluded: Object.keys(excluded) }
    }
    function refresh() { previewTimer.restart() }
    function run() { backend.names.previewPaste(pasteText.text, options()) }
    function setText(text) {
        overrides = ({}); excluded = ({}); column = -1; start = 1; end = 0; chapterChoices = ({})
        pasteText.text = text
    }
    function override(key, kind) {
        const next = Object.assign({}, overrides)
        if (kind === "") delete next[key]; else next[key] = kind
        overrides = next
    }
    function pasteSmart() {
        if (backend.names.clipboardHasImage()) backend.names.ocrClipboard()
        else { pasteText.selectAll(); pasteText.paste(); pasteText.forceActiveFocus() }
    }
    onOpened: {
        if (pasteText.text === "" && win.namesView.pasteDraft !== "") pasteText.text = win.namesView.pasteDraft
        disc = 0
        run()
        pasteText.forceActiveFocus()
    }
    onDiscChanged: refresh()
    onStartChanged: refresh()
    onEndChanged: refresh()
    onModeChanged: refresh()
    onSkipModeChanged: refresh()
    onChapterChoicesChanged: refresh()
    // Click on a chapter: skip it or use it; a choice that matches what was detected is dropped again
    function toggleChapter(c) {
        const next = Object.assign({}, chapterChoices)
        const wantSkip = !c.skipped
        const detectedSkip = skipMode === "auto" && (c.kind === "talk" || c.kind === "interlude")
        if (wantSkip === detectedSkip) delete next[c.number]
        else next[c.number] = wantSkip ? "skip" : "use"
        chapterChoices = next
    }
    onHalfwidthChanged: refresh()
    onSuffixesChanged: refresh()
    onOriginalChanged: refresh()
    onColumnChanged: refresh()
    onOverridesChanged: refresh()
    onExcludedChanged: refresh()
    function toggleLine(key) {
        const next = Object.assign({}, excluded)
        if (next[key]) delete next[key]; else next[key] = true
        excluded = next
    }
    // Every line that lands on a chapter, ticked or not
    function setAllLines(on) {
        const next = ({})
        if (!on) pv.rows.forEach(function(r) { if (r.chapter !== "") next[r.key] = true })
        excluded = next
    }
    Timer { id: previewTimer; interval: 160; onTriggered: dialog.run() }

    // A screenshot was read: add its text (or replace what the same screenshot gave before)
    readonly property int ocrSerial: ocrState.serial
    onOcrSerialChanged: {
        if (ocrState.state !== "done") return
        shotShown = true
        const text = ocrState.text
        const current = pasteText.text
        if (ocrState.again && lastOcr !== "" && current.indexOf(lastOcr) >= 0) pasteText.text = current.replace(lastOcr, text)
        else if (current.trim() === "") setText(text)
        else pasteText.text = current.replace(/\s+$/, "") + "\n\n" + text
        lastOcr = text
    }
    // A web page was read: show its most likely list
    readonly property int webSerial: web.serial
    onWebSerialChanged: {
        if (web.state !== "done" || web.candidates.length === 0) return
        webChoice = 0
        shotShown = false
        setText(web.candidates[0].text)
    }

    function stateText(row) {
        if (row.kind === "merged") return win.tr("pasteMerged")
        if (row.kind === "off") return win.tr("pasteIgnored")
        if (row.kind === "note") return win.tr("pasteNote")
        if (row.state === "otherDisc") return win.tr("pasteOtherDisc")
        if (row.state === "overflow") return win.tr("pasteOverflow")
        if (row.state === "unplaced") return win.tr(row.kind === "song" ? "pasteUnplaced" : "pasteIgnoredByTime")
        if (row.state === "ignored") return win.tr(row.kind === "extra" ? "pasteExtraAuto" : "pasteIgnored")
        if (row.kind === "extra") return win.tr("pasteExtra")
        if (row.kind === "skip") return win.tr("pasteSkip")
        if (row.kind === "header") return win.tr("pasteHeader")
        if (row.kind === "disc") return win.tr("pasteDiscHeading")
        return ""
    }
    function apply() {
        dialog.close()
        backend.names.applyPaste(pasteText.text, options())
    }

    FileDialog {
        id: imagePicker
        title: win.tr("ocrPick")
        nameFilters: [win.tr("ocrImageFilter")]
        onAccepted: backend.names.ocrImage(selectedFile.toString())
    }

    // Change what one line is
    AppMenu {
        id: lineMenu
        property var row: ({})
        AppMenuItem { text: win.tr("lineSong"); checkable: true; checked: lineMenu.row.kind === "song"; onTriggered: dialog.override(lineMenu.row.key, "song") }
        AppMenuItem { text: win.tr("lineExtra"); checkable: true; checked: lineMenu.row.kind === "extra"; onTriggered: dialog.override(lineMenu.row.key, "extra") }
        AppMenuItem { text: win.tr("lineMerge"); checkable: true; checked: lineMenu.row.kind === "merged"; onTriggered: dialog.override(lineMenu.row.key, "merged") }
        AppMenuItem { text: win.tr("lineOff"); checkable: true; checked: lineMenu.row.kind === "off"; onTriggered: dialog.override(lineMenu.row.key, "off") }
        MenuSeparator {
            topPadding: 4; bottomPadding: 4
            contentItem: Rectangle { implicitHeight: 1; color: Theme.line }
        }
        AppMenuItem { text: win.tr("lineAuto"); enabled: lineMenu.row.manual === true; onTriggered: dialog.override(lineMenu.row.key, "") }
    }

    // The screenshot, large
    Popup {
        id: shotView
        parent: Overlay.overlay
        x: 0; y: 0; width: parent ? parent.width : 0; height: parent ? parent.height : 0
        modal: true; padding: 32
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Qt.rgba(0, 0, 0, 0.85) }
        Image {
            anchors.fill: parent; fillMode: Image.PreserveAspectFit; source: dialog.ocrState.image
            asynchronous: true; smooth: true; mipmap: true
            MouseArea { anchors.fill: parent; onClicked: shotView.close() }
        }
    }

    // A small labelled switch
    component OptionSwitch: AbstractButton {
        id: option
        property string label: ""
        property string hint: ""
        checkable: true
        implicitHeight: 26; implicitWidth: optionRow.implicitWidth
        contentItem: RowLayout {
            id: optionRow; spacing: 8
            Toggle { checked: option.checked }
            Copy { text: option.label; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
        }
        background: Item {}
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        ToolTip.visible: hovered && hint !== ""; ToolTip.text: hint; ToolTip.delay: 400
        Accessible.role: Accessible.CheckBox; Accessible.name: label; Accessible.checked: checked
    }

    // A chapter number with a step back / forward on each side
    component Stepper: RowLayout {
        id: stepper
        property int value: 1
        property bool canDown: true
        property bool canUp: true
        property string downName: ""
        property string upName: ""
        signal step(int by)
        spacing: 0
        IconButton {
            iconKind: "back"; implicitWidth: 24; implicitHeight: 26; enabled: stepper.canDown
            onClicked: stepper.step(-1); Accessible.name: stepper.downName
        }
        Copy {
            text: String(stepper.value).padStart(2, "0"); font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(13)
            horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 24
        }
        IconButton {
            iconKind: "back"; implicitWidth: 24; implicitHeight: 26; rotation: 180; enabled: stepper.canUp
            onClicked: stepper.step(1); Accessible.name: stepper.upName
        }
    }
    // One entry of the chapter legend: a small cell and what it means
    component LegendItem: Row {
        id: legend
        property string label: ""
        property color fill: Theme.chip
        property color edge: "transparent"
        property color ink: Theme.sub
        property bool struck: false
        property bool faded: false
        spacing: 6; height: 18
        Rectangle {
            width: 24; height: 16; radius: 4; color: legend.fill; border.color: legend.edge
            opacity: legend.faded ? 0.4 : 1; anchors.verticalCenter: parent.verticalCenter
            Text {
                anchors.centerIn: parent; text: "01"; font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(9)
                font.strikeout: legend.struck; color: legend.ink
            }
        }
        Copy { text: legend.label; font.pixelSize: Theme.px(11); color: Theme.faint; wrapMode: Text.NoWrap; anchors.verticalCenter: parent.verticalCenter }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 14
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            ColumnLayout {
                Layout.fillWidth: true; spacing: 4
                Copy { text: win.tr("paste"); font.pixelSize: Theme.title; font.weight: Theme.strong }
                Copy { text: win.tr("pasteHint"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true }
            }
            ActionButton { text: win.tr("pasteFromClipboard"); implicitHeight: 30; enabled: !win.appView.working; onClicked: dialog.pasteSmart() }
            ActionButton { text: win.tr("ocrPick"); implicitHeight: 30; enabled: !win.appView.working; onClicked: imagePicker.open() }
            ActionButton {
                text: win.tr("pasteClear"); ghost: true; implicitHeight: 30
                enabled: pasteText.text !== ""
                onClicked: { dialog.setText(""); dialog.lastOcr = ""; dialog.shotShown = false; pasteText.forceActiveFocus() }
            }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            // ---------- left: the source
            ColumnLayout {
                Layout.fillHeight: true; Layout.preferredWidth: Math.round(dialog.availableWidth * 0.27)
                Layout.maximumWidth: Math.round(dialog.availableWidth * 0.27)
                spacing: 8
                // From a web page
                RowLayout {
                    Layout.fillWidth: true; spacing: 6
                    Field {
                        id: address
                        Layout.fillWidth: true; implicitHeight: 32
                        placeholderText: win.tr("webPlaceholder")
                        text: dialog.web.url
                        onAccepted: if (text.trim() !== "" && !win.appView.working) backend.names.fetchSetlist(text)
                    }
                    ActionButton {
                        text: dialog.web.state === "running" ? win.tr("webFetchingShort") : win.tr("webFetch")
                        implicitHeight: 32; enabled: address.text.trim() !== "" && !win.appView.working
                        onClicked: backend.names.fetchSetlist(address.text)
                    }
                }
                Copy {
                    visible: dialog.web.state === "failed"
                    text: dialog.web.error; color: Theme.danger; font.pixelSize: Theme.px(11); Layout.fillWidth: true
                }
                // Other lists found on the page
                Flow {
                    Layout.fillWidth: true; spacing: 6
                    visible: dialog.web.state === "done" && dialog.web.candidates.length > 1
                    Copy { text: win.tr("webOthers"); color: Theme.muted; font.pixelSize: Theme.px(11); height: 24; verticalAlignment: Text.AlignVCenter; wrapMode: Text.NoWrap }
                    Repeater {
                        model: dialog.web.state === "done" ? dialog.web.candidates : []
                        delegate: AbstractButton {
                            id: chip
                            required property var modelData
                            required property int index
                            readonly property bool on: index === dialog.webChoice
                            implicitHeight: 24; implicitWidth: chipText.implicitWidth + 16
                            onClicked: { dialog.webChoice = index; dialog.setText(modelData.text) }
                            contentItem: Text {
                                id: chipText
                                text: win.fmt("webCandidate", { k: win.tr("webKind_" + chip.modelData.kind), n: chip.modelData.songs })
                                      + (chip.modelData.heading ? " · " + chip.modelData.heading : "")
                                font.family: Theme.ui; font.pixelSize: Theme.px(11)
                                color: chip.on ? Theme.accentInk : Theme.sub
                                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                            }
                            background: Rectangle { radius: 12; color: chip.on ? Theme.accent : chip.hovered ? Theme.accentSoft : Theme.chip }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                        }
                    }
                }
                // The screenshot being read
                Rectangle {
                    visible: dialog.ocrState.image !== "" && (dialog.shotShown || dialog.ocrState.state === "running"
                                                               || dialog.ocrState.state === "failed")
                    // Grows to fit its text, so nothing (the hide button included) spills over the frame
                    Layout.fillWidth: true; Layout.preferredHeight: Math.max(92, shotInfo.implicitHeight + 16); radius: 10
                    color: Theme.deep; border.color: Theme.line
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 120; Layout.fillHeight: true; radius: 6; color: Theme.chip; clip: true
                            Image {
                                anchors.fill: parent; fillMode: Image.PreserveAspectCrop; verticalAlignment: Image.AlignTop
                                source: dialog.ocrState.image; asynchronous: true; smooth: true; mipmap: true
                                sourceSize.width: 360
                            }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: shotView.open()
                                ToolTip.visible: containsMouse; ToolTip.text: win.tr("ocrEnlarge"); hoverEnabled: true
                            }
                        }
                        ColumnLayout {
                            id: shotInfo
                            // Width from what is left beside the picture, never from the language switch
                            Layout.fillWidth: true; Layout.preferredWidth: 0; Layout.minimumWidth: 0; spacing: 6
                            Copy {
                                Layout.fillWidth: true; font.pixelSize: Theme.px(12)
                                color: dialog.ocrState.state === "failed" ? Theme.danger : Theme.sub
                                text: dialog.ocrState.state === "running" ? win.tr("ocrRunning")
                                    : dialog.ocrState.state === "failed" ? dialog.ocrState.error
                                    : win.tr("ocrDone")
                            }
                            Flow {
                                visible: dialog.ocrState.state === "done" && dialog.ocrState.languages.length > 1
                                Layout.fillWidth: true; spacing: 6
                                Copy { text: win.tr("ocrLanguage"); color: Theme.muted; font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap; height: 22; verticalAlignment: Text.AlignVCenter }
                                Segmented {
                                    itemHeight: 22
                                    options: dialog.ocrState.languages.map(function(tag) { return { key: tag, label: win.tr("ocrLang_" + tag.split("-")[0]) } })
                                    current: dialog.ocrState.language
                                    onPicked: function(key) { if (!win.appView.working) backend.names.ocrAgain(key) }
                                }
                            }
                        }
                        IconButton {
                            Layout.alignment: Qt.AlignTop; iconKind: "close"; implicitWidth: 26; implicitHeight: 26
                            onClicked: dialog.shotShown = false
                            ToolTip.visible: hovered; ToolTip.text: win.tr("ocrHide"); Accessible.name: win.tr("ocrHide")
                        }
                    }
                }
                ScrollView {
                    id: pasteScroll
                    Layout.fillWidth: true; Layout.fillHeight: true
                    // The scroll bar sits inside the box, so the box lines up with the rows above it
                    ScrollBar.vertical: SlimScrollBar {
                        id: pasteBar; parent: pasteScroll; z: 1
                        x: pasteScroll.mirrored ? 3 : pasteScroll.width - width - 3; y: 4; height: pasteScroll.height - 8
                    }
                    TextArea {
                        id: pasteText
                        ContextMenu.menu: EditMenu { target: pasteText }
                        wrapMode: TextEdit.NoWrap; selectByMouse: true; color: Theme.text
                        font.family: Theme.ui; font.pixelSize: Theme.px(13); padding: 12; rightPadding: 12 + pasteBar.gutter
                        placeholderText: win.tr("pastePlaceholder"); placeholderTextColor: Theme.faint
                        onTextChanged: dialog.refresh()
                        // Ctrl+V with a screenshot on the clipboard reads it
                        Keys.onPressed: function(event) {
                            if (event.matches(StandardKey.Paste) && backend.names.clipboardHasImage()) {
                                event.accepted = true
                                if (!win.appView.working) backend.names.ocrClipboard()
                            }
                        }
                        background: Rectangle {
                            color: Theme.field; radius: 10
                            border.color: drop.containsDrag ? Theme.accent : pasteText.activeFocus ? Theme.accent : Theme.line2
                            border.width: drop.containsDrag ? 2 : 1
                        }
                    }
                }
            }
            // ---------- middle: how the list lands on the chapters
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                radius: 10; color: Theme.deep; border.color: Theme.line
                Flickable {
                    id: middleFlick
                    anchors.fill: parent; anchors.margins: 14; clip: true
                    contentHeight: middle.implicitHeight; boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height
                    ScrollBar.vertical: SlimScrollBar { id: middleBar }
                ColumnLayout {
                    id: middle
                    width: middleFlick.width - middleBar.gutter; spacing: 10
                    // Summary
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Copy {
                            Layout.fillWidth: true; font.weight: Font.DemiBold; wrapMode: Text.NoWrap; elide: Text.ElideRight
                            text: dialog.pv.exported ? win.fmt("pasteExportedSummary", { n: dialog.pv.songs })
                                : !dialog.pv.valid ? win.tr("pasteEmpty")
                                : win.fmt(dialog.pv.extras > 0 ? "pasteSummaryExtras" : "pasteSummary",
                                          { s: dialog.pv.songs, e: dialog.pv.extras, u: dialog.pv.used, c: dialog.pv.chapters })
                        }
                        Badge {
                            visible: dialog.pv.valid && !dialog.pv.exported && dialog.pv.overflow > 0
                            tone: "danger"; text: win.fmt(dialog.pv.mode === "duration" ? "pasteUnplacedCount" : "pasteOverflowCount", { n: dialog.pv.overflow })
                        }
                        Badge {
                            visible: dialog.pv.valid && !dialog.pv.exported && dialog.pv.overflow === 0
                                     && dialog.pv.mode === "order" && dialog.pv.free > 0
                            text: win.fmt("pasteChaptersLeft", { n: dialog.pv.free })
                        }
                    }
                    // Options
                    Flow {
                        Layout.fillWidth: true; spacing: 10
                        visible: !dialog.pv.exported
                        Segmented {
                            visible: dialog.pv.discs.length > 1
                            itemHeight: 26
                            options: dialog.pv.discs.map(function(d) { return { key: String(d), label: win.fmt("pasteDiscN", { n: d }) } })
                            current: String(dialog.pv.disc)
                            onPicked: function(key) { dialog.disc = Number(key) }
                        }
                        Segmented {
                            visible: dialog.pv.canDuration
                            itemHeight: 26
                            options: [{ key: "auto", label: win.tr("pasteByDuration") }, { key: "order", label: win.tr("pasteByOrder") }]
                            current: dialog.pv.mode === "duration" ? "auto" : "order"
                            onPicked: function(key) { dialog.mode = key }
                        }
                        // The chapters the list fills: from ... to ...
                        RowLayout {
                            visible: dialog.pv.mode === "order"
                            spacing: 4; height: 26
                            HoverHandler { id: rangeHover }
                            ToolTip.visible: rangeHover.hovered; ToolTip.delay: 600; ToolTip.text: win.tr("pasteRangeHint")
                            Copy { text: win.tr("pasteStartAt"); font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; color: Theme.sub; rightPadding: 2 }
                            Stepper {
                                value: dialog.pv.start
                                canDown: dialog.pv.start > 1; canUp: dialog.pv.start < dialog.pv.end
                                downName: win.tr("pasteStartEarlier"); upName: win.tr("pasteStartLater")
                                onStep: function(by) { dialog.start = dialog.pv.start + by }
                            }
                            Copy { text: win.tr("pasteEndAt"); font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; color: Theme.sub; leftPadding: 4; rightPadding: 2 }
                            Stepper {
                                value: dialog.pv.end
                                canDown: dialog.pv.end > dialog.pv.start; canUp: dialog.pv.end < dialog.pv.chapters
                                downName: win.tr("pasteEndEarlier"); upName: win.tr("pasteEndLater")
                                onStep: function(by) { dialog.end = dialog.pv.end + by }
                            }
                            Copy { visible: text !== ""; text: win.tr("pasteEndChapter"); font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; color: Theme.sub; leftPadding: 2 }
                        }
                        RowLayout {
                            visible: dialog.pv.columns.length > 1
                            spacing: 6; height: 26
                            Copy { text: win.tr("pasteTitleColumn"); font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; color: Theme.sub }
                            Segmented {
                                itemHeight: 26
                                options: dialog.pv.columns
                                current: String(dialog.pv.column)
                                onPicked: function(key) { dialog.column = Number(key) }
                            }
                        }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 16
                        visible: !dialog.pv.exported
                        OptionSwitch {
                            label: win.tr("pasteOriginal"); hint: win.tr("pasteOriginalHint")
                            checked: dialog.original; onToggled: dialog.original = checked
                        }
                        OptionSwitch {
                            label: win.tr("pasteDropSuffix"); hint: win.tr("pasteDropSuffixHint")
                            checked: dialog.suffixes; onToggled: dialog.suffixes = checked
                        }
                        OptionSwitch {
                            label: win.tr("pasteHalfwidth"); hint: win.tr("pasteHalfwidthHint")
                            checked: dialog.halfwidth; onToggled: dialog.halfwidth = checked
                        }
                    }
                    // Chapters: which ones are songs; click one to skip it or use it
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 8
                        visible: !dialog.pv.exported && dialog.pv.mode === "order" && dialog.pv.strip.length > 0
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Copy { text: win.tr("pasteNonSong"); font.pixelSize: Theme.px(12); color: Theme.sub; wrapMode: Text.NoWrap }
                            Segmented {
                                itemHeight: 24
                                options: [{ key: "auto", label: win.tr("pasteSkipAuto") }, { key: "none", label: win.tr("pasteSkipNone") },
                                          { key: "lines", label: win.tr("pasteSkipLines") }]
                                current: dialog.pv.skip
                                onPicked: function(key) { dialog.skipMode = key; dialog.chapterChoices = ({}) }
                            }
                        }
                        Copy {
                            Layout.fillWidth: true
                            font.pixelSize: Theme.px(11); color: Theme.faint
                            text: dialog.pv.skip === "auto"
                                  ? win.fmt(dialog.pv.byWave ? "pasteSkipByWave" : "pasteSkipByLength", { n: dialog.pv.skippedCount })
                                  : dialog.pv.skip === "none" ? win.tr("pasteSkipNoneHint")
                                  : win.tr("pasteSkipLinesHint")
                        }
                        Flow {
                            Layout.fillWidth: true; spacing: 4
                            Repeater {
                                model: dialog.pv.strip
                                delegate: Rectangle {
                                    id: cell
                                    required property var modelData
                                    readonly property var c: modelData
                                    readonly property bool hearing: dialog.listenedHere && win.previewView.previewRow === c.row
                                    width: 66; height: Math.round(40 * Math.max(1, Theme.fontScale)); radius: 6
                                    opacity: c.before ? 0.4 : 1
                                    color: c.skipped ? "transparent" : c.title !== "" ? Theme.accentSoft2 : Theme.chip
                                    border.color: hearing ? Theme.accent : c.skipped ? Theme.line2 : numberHover.hovered ? Theme.accent : "transparent"
                                    border.width: hearing ? 2 : 1
                                    clip: true
                                    // Left: number and length; click to skip / use the chapter
                                    Item {
                                        id: numberArea
                                        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                                        width: parent.width - 22
                                        Column {
                                            anchors.centerIn: parent; spacing: 1
                                            Text {
                                                anchors.horizontalCenter: parent.horizontalCenter; text: cell.c.n
                                                font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(11); font.weight: Font.DemiBold
                                                font.strikeout: cell.c.skipped
                                                color: cell.c.skipped ? Theme.faint : cell.c.title !== "" ? Theme.accentText : Theme.sub
                                            }
                                            Text {
                                                anchors.horizontalCenter: parent.horizontalCenter; text: cell.c.length || "—"
                                                font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(10)
                                                color: Theme.faint
                                            }
                                        }
                                        HoverHandler { id: numberHover; cursorShape: Qt.PointingHandCursor }
                                        TapHandler { onTapped: dialog.toggleChapter(cell.c) }
                                        ToolTip.visible: numberHover.hovered
                                        ToolTip.delay: 300
                                        ToolTip.text: win.fmt("pasteChapterTip", { n: cell.c.n, t: cell.c.length })
                                                      + (cell.c.skipped ? win.tr((cell.c.kind === "talk" || cell.c.kind === "interlude") && !cell.c.manual ? "pasteChapterTalk" : "pasteChapterSkipped")
                                                         : cell.c.title !== "" ? " · " + cell.c.title : win.tr("pasteChapterFree"))
                                                      + "\n" + win.tr(cell.c.skipped ? "pasteChapterClickUse" : "pasteChapterClickSkip")
                                    }
                                    // Right: listen to this chapter
                                    Rectangle {
                                        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.margins: 3
                                        width: 18; radius: 4
                                        color: listenHover.hovered ? Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.1) : "transparent"
                                        Icon {
                                            anchors.centerIn: parent; width: 11; height: 11
                                            visible: !(cell.hearing && win.previewView.previewLoading)
                                            kind: cell.hearing && win.previewPlaying ? "pause" : "play"
                                            ink: cell.hearing ? Theme.accent : cell.c.skipped ? Theme.faint : Theme.sub
                                        }
                                        BusyIndicator {
                                            anchors.centerIn: parent; width: 16; height: 16
                                            running: cell.hearing && win.previewView.previewLoading; visible: running
                                        }
                                        HoverHandler { id: listenHover; cursorShape: Qt.PointingHandCursor }
                                        TapHandler { onTapped: dialog.listen(cell.c) }
                                        ToolTip.visible: listenHover.hovered; ToolTip.delay: 300
                                        ToolTip.text: win.fmt("pasteListenTip", { n: cell.c.n })
                                        Accessible.role: Accessible.Button
                                        Accessible.name: win.fmt("pasteListenTip", { n: cell.c.n })
                                    }
                                    Rectangle {      // set by hand
                                        visible: cell.c.manual
                                        x: numberArea.width - 9; anchors.top: parent.top; anchors.topMargin: 4
                                        width: 5; height: 5; radius: 2.5; color: Theme.accent
                                    }
                                    Text {           // the outline could not tell
                                        visible: cell.c.kind === "unsure" && !cell.c.manual
                                        x: numberArea.width - 10; anchors.top: parent.top; anchors.topMargin: 1
                                        text: "?"; font.pixelSize: Theme.px(9); color: Theme.accentText
                                    }
                                    Rectangle {      // how far it has played
                                        visible: cell.hearing && win.previewDuration > 0
                                        anchors.left: parent.left; anchors.bottom: parent.bottom
                                        height: 3; color: Theme.accent
                                        width: parent.width * Math.min(1, win.previewPosition / Math.max(1, win.previewDuration))
                                    }
                                }
                            }
                        }
                        // What the cells mean
                        Flow {
                            Layout.fillWidth: true; spacing: 14
                            LegendItem { label: win.tr("pasteLegendSong"); fill: Theme.accentSoft2; ink: Theme.accentText }
                            LegendItem { label: win.tr("pasteLegendFree"); fill: Theme.chip; ink: Theme.sub }
                            LegendItem { label: win.tr("pasteLegendSkip"); fill: "transparent"; edge: Theme.line2; ink: Theme.faint; struck: true }
                            LegendItem { label: win.tr("pasteLegendOut"); fill: Theme.chip; ink: Theme.sub; faded: true }
                            Row {
                                spacing: 6; height: 18
                                Rectangle { width: 6; height: 6; radius: 3; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                                Copy { text: win.tr("pasteLegendManual"); font.pixelSize: Theme.px(11); color: Theme.faint; wrapMode: Text.NoWrap; anchors.verticalCenter: parent.verticalCenter }
                            }
                            Row {
                                spacing: 6; height: 18
                                Text { text: "?"; font.pixelSize: Theme.px(11); font.bold: true; color: Theme.accentText; anchors.verticalCenter: parent.verticalCenter }
                                Copy { text: win.tr("pasteLegendUnsure"); font.pixelSize: Theme.px(11); color: Theme.faint; wrapMode: Text.NoWrap; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }
                        // The chapter heard from here: play / pause, seek, stop
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 44
                            visible: dialog.listenedHere && win.previewView.previewRow >= 0
                            radius: 8; color: Theme.raised; border.color: Theme.line2
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 6; anchors.rightMargin: 8; spacing: 8
                                IconButton {
                                    iconKind: win.previewPlaying ? "pause" : "play"; implicitWidth: 30; implicitHeight: 30
                                    enabled: !win.previewView.previewLoading
                                    onClicked: win.togglePreview()
                                    Accessible.name: win.tr(win.previewPlaying ? "previewPause" : "previewPlay")
                                }
                                Copy {
                                    text: win.fmt("pasteNowPlaying", { n: String(win.previewView.previewRow + 1).padStart(2, "0") })
                                    font.pixelSize: Theme.px(12); font.weight: Font.DemiBold; color: Theme.accentText; wrapMode: Text.NoWrap
                                }
                                Item {
                                    Layout.fillWidth: true; Layout.preferredHeight: 22
                                    WaveSeek {
                                        anchors.fill: parent
                                        visible: !win.previewView.previewLoading
                                        peaks: backend.preview.previewWave; showWave: backend.config.waveform !== false
                                        position: win.previewPosition; duration: win.previewDuration; interactive: win.previewSeekable
                                        onMoved: function(ms) { win.seekPreview(ms) }
                                    }
                                    BusyIndicator { anchors.centerIn: parent; width: 18; height: 18; running: win.previewView.previewLoading; visible: running }
                                }
                                Copy {
                                    text: dialog.clock(win.previewPosition) + " / " + dialog.clock(win.previewDuration)
                                    font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(11); color: Theme.muted; wrapMode: Text.NoWrap
                                }
                                IconButton {
                                    iconKind: "close"; implicitWidth: 26; implicitHeight: 26
                                    onClicked: { backend.preview.stopPreview(); dialog.listenedHere = false }
                                    ToolTip.visible: hovered; ToolTip.text: win.tr("pasteListenStop"); Accessible.name: win.tr("pasteListenStop")
                                }
                            }
                        }
                    }
                }
                }
            }
            // ---------- right: what each line becomes
            Rectangle {
                Layout.fillHeight: true; Layout.preferredWidth: Math.round(dialog.availableWidth * 0.28)
                radius: 10; color: Theme.deep; border.color: Theme.line
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; anchors.rightMargin: 6; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true; Layout.rightMargin: 8; spacing: 8
                        Copy { text: win.tr("pasteRowsTitle"); font.weight: Font.DemiBold; wrapMode: Text.NoWrap }
                        Copy {
                            visible: dialog.pv.valid && !dialog.pv.exported && dialog.pv.kept < dialog.pv.used
                            text: win.fmt("pasteKept", { k: dialog.pv.kept, n: dialog.pv.used })
                            font.pixelSize: Theme.px(11); color: Theme.accentText; wrapMode: Text.NoWrap
                        }
                        Copy { text: win.tr("pasteRowsHint"); font.pixelSize: Theme.px(11); color: Theme.faint; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight; horizontalAlignment: Text.AlignRight }
                        ActionButton {
                            readonly property bool allOn: dialog.pv.kept === dialog.pv.used
                            visible: dialog.pv.valid && !dialog.pv.exported && dialog.pv.used > 0
                            text: win.tr(allOn ? "selectNone" : "selectAll"); ghost: true; implicitHeight: 24
                            onClicked: dialog.setAllLines(!allOn)
                        }
                    }
                    ListView {
                        id: rowsView
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; spacing: 2
                        model: dialog.pv.rows
                        ScrollBar.vertical: SlimScrollBar { id: rowsBar }
                        delegate: Rectangle {
                            id: line
                            required property var modelData
                            readonly property var r: modelData
                            readonly property bool lands: r.chapter !== ""
                            readonly property bool off: r.excluded === true
                            readonly property bool editable: r.kind !== "disc" && r.kind !== "skip"
                            readonly property bool dim: r.kind === "header" || r.kind === "note" || r.kind === "off"
                                                        || r.kind === "merged" || r.state === "otherDisc" || r.state === "ignored"
                            width: rowsView.width - Math.max(8, rowsBar.gutter); height: r.kind === "disc" ? 30 : 28; radius: 6
                            color: r.kind === "disc" ? Theme.chip : lineHover.hovered && editable ? Theme.raised : "transparent"
                            HoverHandler { id: lineHover; cursorShape: line.editable ? Qt.PointingHandCursor : Qt.ArrowCursor }
                            TapHandler {
                                enabled: line.editable
                                onTapped: { lineMenu.row = line.r; lineMenu.popup() }
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 6; anchors.rightMargin: 6; spacing: 8
                                // Tick: use this line's title (unticked: the chapter keeps its current name)
                                Item {
                                    Layout.preferredWidth: 22; Layout.fillHeight: true
                                    visible: line.r.kind !== "disc"
                                    SelectionMark {
                                        anchors.centerIn: parent; visible: line.lands
                                        checked: !line.off; scale: 0.9
                                    }
                                    // A MouseArea takes the click, so the row's own menu does not open as well
                                    MouseArea {
                                        anchors.fill: parent; enabled: line.lands; cursorShape: Qt.PointingHandCursor
                                        onClicked: dialog.toggleLine(line.r.key)
                                    }
                                    Accessible.role: Accessible.CheckBox; Accessible.checked: !line.off
                                    Accessible.name: win.tr("pasteUseLine") + " " + line.r.title
                                }
                                Rectangle {
                                    opacity: line.off ? 0.45 : 1
                                    Layout.preferredWidth: 30; Layout.preferredHeight: 20; radius: 5
                                    visible: line.r.kind !== "disc"
                                    color: !line.lands ? "transparent" : line.r.kind === "song" ? Theme.accentSoft2 : Theme.chip
                                    border.color: line.lands ? "transparent" : Theme.line2
                                    Text {
                                        anchors.centerIn: parent; font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(11)
                                        text: line.lands ? line.r.chapter : "—"
                                        color: line.lands && line.r.kind === "song" ? Theme.accentText : Theme.faint
                                    }
                                }
                                Copy {
                                    Layout.fillWidth: true; Layout.minimumWidth: 60; wrapMode: Text.NoWrap; elide: Text.ElideRight
                                    text: line.r.kind === "skip" ? win.tr("pasteSkipLine") : line.r.title
                                    font.pixelSize: Theme.px(line.r.kind === "disc" ? 12 : 13)
                                    font.weight: line.r.kind === "disc" ? Font.DemiBold : Font.Normal
                                    font.strikeout: line.r.state === "overflow" || line.r.kind === "off"
                                    color: line.dim || line.off ? Theme.faint : line.r.kind === "song" && line.r.state === "song" ? Theme.text : Theme.sub
                                }
                                Rectangle {
                                    visible: line.r.manual === true
                                    Layout.preferredWidth: manualText.implicitWidth + 10; Layout.preferredHeight: 18; radius: 9
                                    color: Theme.accentSoft
                                    Text { id: manualText; anchors.centerIn: parent; text: win.tr("pasteManual"); font.family: Theme.ui; font.pixelSize: Theme.px(10); color: Theme.accentText }
                                }
                                Copy {
                                    visible: text !== ""
                                    text: dialog.stateText(line.r)
                                    font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap
                                    color: line.r.state === "overflow" || line.r.state === "unplaced" ? Theme.pendingText : Theme.faint
                                }
                                Copy {
                                    visible: line.r.time !== "" || line.r.chapterTime !== ""
                                    horizontalAlignment: Text.AlignRight
                                    font.family: Theme.num; font.features: Theme.tabular; font.pixelSize: Theme.px(11); wrapMode: Text.NoWrap; color: Theme.faint
                                    text: line.r.time !== "" && line.r.chapterTime !== "" ? line.r.time + " / " + line.r.chapterTime
                                        : line.r.time !== "" ? line.r.time : line.r.chapterTime
                                }
                            }
                        }
                        Copy {
                            anchors.centerIn: parent; visible: rowsView.count === 0
                            text: win.tr("pasteRightEmpty"); color: Theme.faint; horizontalAlignment: Text.AlignHCenter
                            width: parent.width * 0.8
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Copy {
                Layout.fillWidth: true; color: Theme.muted; font.pixelSize: Theme.px(12); elide: Text.ElideRight; wrapMode: Text.NoWrap
                text: dialog.pv.exported ? win.tr("pasteExportedTracklist") : win.tr("pasteFootnote")
            }
            ActionButton { text: win.tr("cancel"); onClicked: dialog.close() }
            ActionButton { text: win.tr("preview"); primary: true; enabled: dialog.pv.valid && !win.appView.working; onClicked: dialog.apply() }
        }
    }

    // Drop a screenshot (or a link) anywhere on the dialog
    DropArea {
        id: drop
        anchors.fill: parent
        keys: ["text/uri-list", "text/plain"]
        onDropped: function(event) {
            if (win.appView.working) return          // another job holds the worker: same rule as the buttons
            if (event.hasUrls && event.urls.length > 0) {
                const url = event.urls[0].toString()
                if (url.startsWith("http")) { address.text = url; backend.names.fetchSetlist(url) }
                else backend.names.ocrImage(url)
                event.accept()
            } else if (event.hasText && /^https?:\/\//.test(event.text.trim())) {
                address.text = event.text.trim(); backend.names.fetchSetlist(address.text); event.accept()
            }
        }
    }
}
