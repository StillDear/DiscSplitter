import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
ApplicationWindow {
    id: rootWindow
    width: 1280; height: 800; minimumWidth: 1100; minimumHeight: 700
    visible: true; title: "DiscSplitter"; color: flush ? Theme.panel : Theme.bg
    font.family: Theme.ui; font.pixelSize: Theme.px(13)
    palette.window: Theme.panel; palette.windowText: Theme.text
    palette.base: Theme.field; palette.text: Theme.text
    palette.button: Theme.raised; palette.buttonText: Theme.text
    palette.highlight: Theme.accent; palette.highlightedText: Theme.accentInk
    property var win: rootWindow
    // The UI state, one slice per area: a change in one re-evaluates only the bindings that read it.
    property var appView: backend.view
    property var discView: backend.disc.view
    property var previewView: backend.preview.view
    property var namesView: backend.names.view
    property var metaView: backend.metadata.view
    property var exportView: backend.exporter.view
    property var t: backend.texts
    property string dialogKind: ""
    property string dialogMessage: ""
    property string browseKind: "source"
    property string toolName: ""
    property bool allowClose: false
    function tr(key) { return t[key] || key }
    function fmt(key, values) {
        let text = tr(key)
        for (const name in values) text = text.split("{" + name + "}").join(String(values[name]))
        return text
    }
    // Playback wording: "试听" (listen) for audio, "播放" when a video is being previewed (key + "Video").
    function playTr(key, video) { return video && t[key + "Video"] ? t[key + "Video"] : tr(key) }
    readonly property bool videoMode: discView.outputFormat !== "flac" && !!discView.hasVideo
    // Pickers open where the current choice is: the export folder, or the folder the open disc is in.
    function startAt(dialog, path, parent) {
        const url = backend.startFolder(path || "", parent)
        if (url !== "") dialog.currentFolder = url
    }
    function openFolder(kind) {
        browseKind = kind
        startAt(folderDialog, kind === "source" ? discView.source : discView.output, kind === "source")
        folderDialog.open()
    }
    function openSourceFile() { startAt(sourceFileDialog, discView.source, true); sourceFileDialog.open() }
    function browseTool(tool) { toolName = tool; toolDialog.open() }
    function pasteTracklist() { pastePopup.open() }
    function openHelp(button) { helpMenu.popup(button, button.width - helpMenu.width, button.height + 4) }
    // The workspace carries its own header pieces (name, mode, language, settings) in its columns.
    // Only the start page has a title bar (language, settings, help); every other page carries its
    // own back button and title, and the export / done pages need none.
    readonly property bool headerShown: appView.page === "start"
    // The workspace is one surface filling the window edge to edge (no frame of background around it).
    readonly property bool flush: appView.page === "main" || appView.page === "review" || appView.page === "metadata"
    readonly property bool previewPlaying: previewBar.playing
    readonly property real previewPosition: previewBar.position
    readonly property real previewDuration: previewBar.duration
    function togglePreview() { previewBar.toggle() }
    readonly property bool previewSeekable: previewBar.seekable
    function seekPreview(ms) { previewBar.seek(ms) }
    // Play a chapter from `ms` into it: seek when it is already the one playing, else load its clip there.
    function previewFrom(row, ms) {
        if (row === previewView.previewRow && previewView.previewUrl !== "") { previewBar.seek(ms); if (!previewPlaying) togglePreview(); return }
        previewBar.startAt = { row: row, ms: Math.max(0, Math.round(ms)) }
        backend.preview.previewChapter(row, -1)
    }
    // Paths as the system writes them (D:\Music\…), wherever one is shown; breakablePath may wrap after a separator.
    function nativePath(path) { return Qt.platform.os === "windows" ? String(path || "").replace(/\//g, "\\") : String(path || "") }
    function breakablePath(path) { return nativePath(path).replace(/([\\/])/g, "$1\u200b") }
    function showTrackInfo(kind, row) { backend.disc.showTrackInfo(kind, row); trackInfoDialog.open() }
    // An open dialog is never replaced: a request that arrives meanwhile waits until it closes, so a
    // pending choice (collision, resume...) cannot be overwritten and lose its cancel-on-dismiss.
    property var dialogQueue: []
    function showDialog(kind, message) {
        if (modal.opened) { dialogQueue = dialogQueue.concat([{ kind: kind, message: message }]); return }
        dialogKind = kind; dialogMessage = message; modal.open()
    }
    function closeDialog() { modal.close() }
    function smokePage(page) { backend.navigate(page) }
    function smokeSection(section) { settingsPage.section = section }
    function smokeHelp(section) { backend.help(section) }
    function smokeHelpMenu() { backend.navigate("start"); helpMenu.popup(rootWindow.contentItem, rootWindow.width - helpMenu.width - 16, 48) }
    function closeHelpMenu() { helpMenu.close() }
    onClosing: function(event) { if (!allowClose) { event.accepted = false; backend.requestClose() } }
    Connections {
        target: backend
        function onDialogRequested(kind, message) { win.showDialog(kind, message) }
        function onQuitReady() { win.allowClose = true; win.close() }
    }
    FolderDialog {
        id: folderDialog
        title: win.tr(win.browseKind === "source" ? "source" : "output")
        onAccepted: {
            if (win.browseKind === "source") backend.disc.setSource(selectedFolder.toString())
            else backend.disc.setOutput(selectedFolder.toString())
        }
    }
    FileDialog {
        id: sourceFileDialog
        title: win.tr("chooseSourceFile")
        nameFilters: [win.tr("sourceFileFilter")]
        onAccepted: backend.disc.setSource(selectedFile.toString())
    }
    FileDialog {
        id: toolDialog
        title: win.tr("tools")
        nameFilters: [win.tr("executableFilter"), win.tr("allFilesFilter")]
        onAccepted: backend.locateTool(win.toolName, selectedFile.toString())
    }
    AppMenu {
        id: helpMenu
        minWidth: 232
        // Learn, then get unstuck, then about: everything opens in the app except the row marked as leaving it.
        AppMenuItem { text: win.tr("helpGuide"); iconKind: "book"; hint: "F1"; onTriggered: backend.help("guide") }
        AppMenuItem { text: win.tr("tips"); iconKind: "bulb"; onTriggered: backend.help("tips") }
        AppMenuItem { text: win.tr("helpFaq"); iconKind: "help"; onTriggered: backend.help("faq") }
        MenuSeparator {
            topPadding: 4; bottomPadding: 4
            contentItem: Rectangle { implicitHeight: 1; color: Theme.line }
        }
        AppMenuItem { text: win.tr("helpTroubleshootMenu"); iconKind: "lifebuoy"; onTriggered: backend.help("troubleshoot") }
        AppMenuItem { text: win.tr("projectHome"); iconKind: "external"; external: true; onTriggered: backend.help("readme") }
        MenuSeparator {
            topPadding: 4; bottomPadding: 4
            contentItem: Rectangle { implicitHeight: 1; color: Theme.line }
        }
        AppMenuItem { text: win.tr("aboutApp"); iconKind: "info"; onTriggered: backend.help("about") }
    }
    // F1 opens the guide from any page (the help button sits only on the start page and the workspace).
    Shortcut { sequence: "F1"; context: Qt.ApplicationShortcut; onActivated: backend.help("guide") }

    ColumnLayout {
        id: pageColumn
        anchors.fill: parent; anchors.leftMargin: win.flush ? 0 : 12; anchors.rightMargin: win.flush ? 0 : 12
        anchors.topMargin: win.flush || win.headerShown ? 0 : 12
        anchors.bottomMargin: win.flush ? 0 : 12; spacing: win.flush ? 0 : 12

        // Title bar (every page but the workspace)
        RowLayout {
            visible: win.headerShown
            Layout.fillWidth: true; Layout.preferredHeight: 44; spacing: 8
            ActionButton {
                visible: (win.appView.page === "review" || win.appView.page === "settings" || win.appView.page === "metadata") && !win.appView.pipeline
                ghost: true; text: "  " + win.tr("back"); enabled: !win.appView.working || win.appView.page === "settings"
                leftPadding: 30; implicitWidth: contentItem.implicitWidth + 40
                onClicked: backend.back()
                Icon { kind: "back"; ink: Theme.text; width: 14; height: 14; anchors.verticalCenter: parent.verticalCenter; x: 10 }
            }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: win.appView.working && !win.appView.pipeline; visible: running; Layout.preferredWidth: 22; Layout.preferredHeight: 22 }
            Copy { visible: win.appView.working && !win.appView.pipeline; text: win.tr(win.appView.status); color: Theme.muted; wrapMode: Text.NoWrap }
            // Language, settings and help: on the workspace, and on the start page (before any disc
            // is open it is the only way to the settings, e.g. to point at a missing tool).
            Segmented {
                visible: win.appView.page === "start"
                itemHeight: 24
                options: [{ key: "zh", label: "中文" }, { key: "en", label: "EN" }]
                current: backend.config.language
                onPicked: function(key) { backend.setPreference("language", key) }
            }
            IconButton { visible: win.appView.page === "start"; iconKind: "gear"; enabled: !win.appView.working; onClicked: backend.navigate("settings"); ToolTip.visible: hovered; ToolTip.text: win.tr("settings"); Accessible.name: win.tr("settings") }
            IconButton { id: helpButton; visible: win.appView.page === "start"; iconKind: "help"; onClicked: win.openHelp(helpButton); ToolTip.visible: hovered; ToolTip.text: win.tr("help"); Accessible.name: win.tr("help") }
        }

        StackLayout {
            id: stack
            // Gives way to the preview panel below: the pages scroll, the panel's controls must stay in view.
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
            currentIndex: ["start", "main", "review", "export", "done", "settings", "metadata", "help"].indexOf(win.appView.page)
            // Page entrance: fade in while settling from a slight zoom.
            onCurrentIndexChanged: {
                const page = currentIndex >= 0 ? children[currentIndex] : null
                if (!page) return
                pageIn.stop(); pageIn.page = page; pageIn.start()
            }
            ParallelAnimation {
                id: pageIn
                property Item page: null
                NumberAnimation { target: pageIn.page; property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageIn.page; property: "scale"; from: Theme.animate ? 0.985 : 1; to: 1; duration: Theme.slow; easing.type: Easing.OutCubic }
            }
            StartPage { win: rootWindow }
            Workspace { id: workspace; win: rootWindow }
            ReviewPage { id: reviewPage; win: rootWindow }
            ExportPage { win: rootWindow }
            DonePage { win: rootWindow }
            SettingsPage { id: settingsPage; win: rootWindow }
            MetadataPage { id: metadataPage; win: rootWindow }
            HelpPage { id: helpPage; win: rootWindow }
        }

        // The preview panel and its height handle. On the pages with a panel down the right (workspace, review,
        // metadata) it docks under the rest, so that panel keeps the full height; elsewhere it runs along the
        // bottom of the window.
        ColumnLayout {
            id: previewArea
            parent: ({ main: workspace.previewSlot, review: reviewPage.previewSlot,
                       metadata: metadataPage.previewSlot })[win.appView.page] || pageColumn
            // (not previewBar.visible: a hidden parent hides the bar too, and it could never come back)
            // Settings and help show no player: what is playing goes on in the background and the panel is back on leaving.
            visible: previewBar.Layout.preferredHeight > 0 && win.appView.page !== "settings" && win.appView.page !== "help"
            Layout.fillWidth: true; Layout.fillHeight: false; spacing: 0   // as tall as the panel, not a share of the page
            Splitter {
                vertical: false; visible: previewBar.visible && previewBar.video
                // Takes no room of its own: it overlaps the gap (or, flush, the hairline) between the two.
                // Centred on the gap above the panel: the page spacing (12, or none when flush) plus its own 12 px.
                Layout.fillWidth: true; Layout.topMargin: win.flush ? -6 : -12; Layout.bottomMargin: win.flush ? -6 : 0
                z: 1
                size: previewBar.videoHeight; direction: -1
                minimum: previewBar.minimumVideoHeight; maximum: previewBar.maximumVideoHeight
                onResized: function(value) { previewBar.heightLive = value }
                onCommitted: function(value) { backend.setLayoutSize("preview_ratio", value / rootWindow.height); previewBar.heightLive = -1 }
                onReset: backend.setLayoutSize("preview_ratio", -1)
            }
            PreviewBar { id: previewBar; win: rootWindow; flush: win.flush }
        }
    }

    TrackInfoDialog { id: trackInfoDialog; win: rootWindow }

    // Paste tracklist
    PasteDialog { id: pastePopup; win: rootWindow }

    // Confirmations and notices
    Popup {
        id: modal
        anchors.centerIn: parent; width: win.dialogKind === "tools" ? 640 : 560
        height: Math.min(win.dialogKind === "tools" || win.dialogKind === "collision" ? 500 : 380, win.height - 100)
        modal: true; padding: 24; closePolicy: Popup.CloseOnEscape
        // Dismissed without choosing (Escape / Cancel): the prepared export is dropped. The choice buttons clear
        // dialogKind first, so they never cancel what they are about to start.
        onAboutToHide: { if (["collision", "duplicate", "resume", "diskSpace"].indexOf(win.dialogKind) >= 0) backend.exporter.cancelExport() }
        onClosed: {
            if (win.dialogQueue.length === 0) return
            const next = win.dialogQueue[0]
            win.dialogQueue = win.dialogQueue.slice(1)
            win.showDialog(next.kind, next.message)
        }
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
                NumberAnimation { property: "scale"; from: Theme.animate ? 0.96 : 1; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast }
                NumberAnimation { property: "scale"; from: 1; to: Theme.animate ? 0.98 : 1; duration: Theme.fast }
            }
        }
        Overlay.modal: Rectangle {
            color: Qt.rgba(0, 0, 0, Theme.light ? 0.25 : 0.5)
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        }
        background: Rectangle { color: Theme.panel; radius: 14; border.color: Theme.line2 }
        ColumnLayout {
            anchors.fill: parent; spacing: 14
            Copy {
                // A kind's own heading ("discardTitle", "resumeTitle") wins over its button-sized name.
                text: win.dialogKind === "tools" ? win.tr("missingTools") : (win.t[win.dialogKind + "Title"] || win.tr(win.dialogKind))
                font.pixelSize: Theme.title; font.weight: Theme.strong; Layout.fillWidth: true
            }
            Copy {
                visible: win.dialogKind === "collision"
                text: win.nativePath(win.discView.output); font.family: Theme.mono; font.pixelSize: Theme.px(12); color: Theme.muted; Layout.fillWidth: true; elide: Text.ElideMiddle; maximumLineCount: 1
            }
            Copy {
                visible: win.dialogKind === "duplicate" || win.dialogKind === "collision"
                text: win.exportView.exportConfirmation; color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true
            }
            ScrollView {
                id: messageScroll
                rightPadding: messageBar.gutter
                ScrollBar.vertical: SlimScrollBar { id: messageBar; parent: messageScroll; x: messageScroll.mirrored ? 0 : messageScroll.width - width; y: messageScroll.topPadding; height: messageScroll.availableHeight }
                Layout.fillWidth: true; Layout.fillHeight: win.dialogKind !== "tools" && win.dialogKind !== "collision"
                Layout.preferredHeight: win.dialogKind === "tools" || win.dialogKind === "collision" ? Math.min(80, implicitHeight) : -1
                clip: true
                TextArea {
                    id: dialogText
                    ContextMenu.menu: EditMenu { target: dialogText }
                    text: win.dialogMessage; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.muted; font.family: Theme.ui; font.pixelSize: Theme.px(13); padding: 0; background: null }
            }
            SettingGroup {
                visible: win.dialogKind === "tools"
                Repeater { model: toolModel; delegate: ToolRow { win: rootWindow } }
            }
            ScrollView {
                id: collisionScroll
                rightPadding: collisionBar.gutter
                ScrollBar.vertical: SlimScrollBar { id: collisionBar; parent: collisionScroll; x: collisionScroll.mirrored ? 0 : collisionScroll.width - width; y: collisionScroll.topPadding; height: collisionScroll.availableHeight }
                visible: win.dialogKind === "collision"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                SettingGroup {
                    width: collisionScroll.availableWidth
                    Repeater {
                        model: win.exportView.collisionFiles
                        SettingRow { required property string modelData; required property int index; first: index === 0; title: modelData; hint: ""; implicitHeight: 44 }
                    }
                }
            }
            Item { visible: win.dialogKind === "tools"; Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                ActionButton { text: win.dialogKind === "tools" ? win.tr("later") : win.tr("cancel"); onClicked: modal.close() }
                // Where a problem is reported, a way to the troubleshooting help (not over a running export).
                ActionButton {
                    visible: (win.dialogKind === "tools" || win.dialogKind === "error") && !win.appView.pipeline
                    text: win.tr("helpMore"); ghost: true
                    onClicked: { modal.close(); backend.help(win.dialogKind === "tools" ? "faq" : "troubleshoot") }
                }
                Item { Layout.fillWidth: true }
                ActionButton { visible: win.dialogKind === "tools"; text: win.tr("checkTools"); enabled: !win.appView.working; primary: true; onClicked: { modal.close(); backend.checkTools() } }
                ActionButton { visible: win.dialogKind === "collision" || win.dialogKind === "diskSpace"; text: win.tr("anotherFolder"); onClicked: { modal.close(); win.openFolder("output") } }
                ActionButton { visible: win.dialogKind === "diskSpace"; text: win.tr("exportAnyway"); danger: true; onClicked: { win.dialogKind = ""; modal.close(); backend.exporter.exportDespiteSpace() } }
                ActionButton { visible: win.dialogKind === "collision"; text: win.tr("skipExisting"); onClicked: { win.dialogKind = ""; modal.close(); backend.exporter.skipExisting() } }
                ActionButton { visible: win.dialogKind === "collision"; text: win.tr("overwrite"); danger: true; onClicked: { win.dialogKind = ""; modal.close(); backend.exporter.approveOverwrite() } }
                ActionButton { visible: win.dialogKind === "resume"; text: win.tr("fresh"); onClicked: { win.dialogKind = ""; modal.close(); backend.exporter.fresh() } }
                ActionButton {
                    visible: ["discard", "resume", "duplicate", "closeBusy"].indexOf(win.dialogKind) >= 0
                    text: win.tr(({ discard: "discard", resume: "resume", duplicate: "exportAnyway", closeBusy: "closeAnyway" })[win.dialogKind] || "confirm")
                    primary: win.dialogKind !== "discard"; danger: win.dialogKind === "discard"
                    onClicked: {
                        let kind = win.dialogKind; win.dialogKind = ""; modal.close()
                        if (kind === "discard") backend.exporter.discard()
                        if (kind === "resume") backend.exporter.resume()
                        if (kind === "duplicate") backend.exporter.check_collisions()
                        if (kind === "closeBusy") backend.closeWhenReady()
                    }
                }
            }
        }
    }
}
