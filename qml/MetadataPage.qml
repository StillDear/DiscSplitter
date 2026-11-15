import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
// One surface filling the window, like the review page: cover | album and per-track tags |
// online lookup, divided by draggable hairlines. The page carries its own header (back, title).
RowLayout {
    id: metaPage
    required property var win
    readonly property var meta: win.metaView.meta || ({ album: {}, track_artists: {}, cover: "" })
    readonly property string coverUrl: meta.cover ? "file:///" + String(meta.cover).replace(/\\/g, "/") : ""
    property string source: backend.config.meta_source || "musicbrainz"
    property bool applyAlbum: true
    property bool applyCover: true
    property bool applyArtists: true
    property bool applyTitles: false
    // Panel widths: dragged live (…Live), otherwise the saved layout, otherwise the default.
    readonly property var layoutSizes: backend.config.layout || ({})
    readonly property int centerMinimum: 420
    // A saved width never squeezes the middle panel when the window is narrower than when it was set.
    function fit(value, share) { return Math.max(200, Math.min(value, (win.width - 24) * share)) }
    property real leftLive: -1
    property real rightLive: -1
    readonly property real leftWidth: leftLive > 0 ? leftLive : fit(layoutSizes.meta_left || 300, 0.32)
    readonly property real rightWidth: rightLive > 0 ? rightLive : fit(layoutSizes.meta_right || 360, 0.36)
    readonly property string status: win.metaView.metaStatus || "idle"
    readonly property bool anyApply: applyAlbum || applyCover || applyArtists || applyTitles
    function searchOnline() {
        if (!win.appView.working)
            backend.metadata.metaSearch(source, qArtist.text, qAlbum.text, metaBarcodeToggle.open ? qBarcode.text : "")
    }
    // Up / Down in a track-artist field: carry on in the row above or below.
    function editArtistAt(row) {
        if (row < 0 || row >= tagList.count) return
        tagList.positionViewAtIndex(row, ListView.Contain)
        const item = tagList.itemAtIndex(row)
        if (!item) return
        item.artistField.forceActiveFocus()
        item.artistField.cursorPosition = item.artistField.length
    }
    spacing: 0

    component Label: Copy { color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }

    FileDialog {
        id: coverDialog
        title: win.tr("cover")
        nameFilters: [win.tr("imageFilter")]
        onAccepted: backend.metadata.chooseCover(selectedFile.toString())
    }
    CoverCropDialog { id: cropDialog; objectName: "coverCrop"; win: metaPage.win }

    // The preview panel (from Main) docks here, under the page's main content; the panel on the right
    // runs the full height beside it.
    property alias previewSlot: previewSlot
    ColumnLayout {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0; spacing: 0
    RowLayout {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; spacing: metaPage.spacing
    // ---------- Left: header and cover ----------
    Card {
        flat: true; padding: 20
        Layout.preferredWidth: metaPage.leftWidth; Layout.fillHeight: true
        ColumnLayout {
            anchors.fill: parent; spacing: 14
            RowLayout {
                Layout.fillWidth: true; spacing: 10
                IconButton {
                    visible: !win.appView.pipeline; iconKind: "back"; implicitWidth: 32; implicitHeight: 32
                    enabled: !win.appView.working; Layout.leftMargin: -6
                    onClicked: backend.back()
                    ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("back"); Accessible.name: win.tr("back")
                }
                Copy { text: win.tr("metadata"); font.pixelSize: Theme.display; font.weight: Theme.strong; wrapMode: Text.NoWrap; Layout.fillWidth: true; elide: Text.ElideRight }
                BusyIndicator { running: win.appView.working && !win.appView.pipeline; visible: running; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
            }

            SectionTitle { text: win.tr("cover"); note: win.metaView.coverInfo || ""; Layout.fillWidth: true; Layout.topMargin: 4 }
            Rectangle {
                id: coverFrame
                readonly property bool empty: coverImage.status !== Image.Ready
                Layout.fillWidth: true; Layout.preferredHeight: width; radius: 10
                color: Theme.raised; clip: true
                border.color: coverDrop.containsDrag ? Theme.accent : empty && coverHover.hovered ? Theme.line2 : Theme.line
                border.width: coverDrop.containsDrag ? 2 : 1
                Behavior on border.color { ColorAnimation { duration: Theme.fast } }
                Image {
                    id: coverImage
                    anchors.fill: parent; anchors.margins: 1
                    source: metaPage.coverUrl; fillMode: Image.PreserveAspectFit
                    asynchronous: true; cache: false; sourceSize.width: 600
                    opacity: status === Image.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                }
                ColumnLayout {
                    anchors.centerIn: parent; width: parent.width - 32; spacing: 8; visible: coverFrame.empty
                    Icon { kind: "disc"; ink: Theme.faint; Layout.preferredWidth: 40; Layout.preferredHeight: 40; Layout.alignment: Qt.AlignHCenter }
                    Copy { text: win.tr("noCover"); color: Theme.sub; Layout.alignment: Qt.AlignHCenter }
                    Copy { text: win.tr("coverDropHint"); color: Theme.faint; font.pixelSize: Theme.px(12); horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                }
                // Cropped: say so on the picture, where the change shows
                Badge {
                    visible: !!win.metaView.canRestoreCover && !coverFrame.empty
                    anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 10
                    tone: "accent"; text: win.tr("coverCropped")
                }
                HoverHandler { id: coverHover; cursorShape: coverFrame.empty ? Qt.PointingHandCursor : Qt.ArrowCursor }
                TapHandler { enabled: coverFrame.empty && !win.appView.working; onTapped: coverDialog.open() }
                DropArea {
                    id: coverDrop
                    anchors.fill: parent
                    onDropped: function(event) { if (event.hasUrls) backend.metadata.chooseCover(event.urls[0].toString()) }
                }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                ActionButton { text: win.tr(metaPage.meta.cover ? "replaceCover" : "chooseCover"); Layout.fillWidth: true; enabled: !win.appView.working; onClicked: coverDialog.open() }
                ActionButton { text: win.tr("removeCover"); ghost: true; visible: !!metaPage.meta.cover; enabled: !win.appView.working; onClicked: backend.metadata.clearCover() }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 8; visible: !!metaPage.meta.cover
                ActionButton { text: win.tr("cropCover"); Layout.fillWidth: true; enabled: !win.appView.working; onClicked: cropDialog.showCover() }
                ActionButton { text: win.tr("cropRestore"); ghost: true; visible: !!win.metaView.canRestoreCover; enabled: !win.appView.working; onClicked: backend.metadata.restoreCover() }
            }
            Copy { text: win.tr("coverHint"); color: Theme.faint; font.pixelSize: Theme.px(12); Layout.fillWidth: true; lineHeight: 1.3 }
            Item { Layout.fillHeight: true }
        }
    }

    Splitter {
        Layout.fillHeight: true; Layout.leftMargin: -6; Layout.rightMargin: -6; z: 1; divider: true
        size: metaPage.leftWidth; direction: 1; minimum: 240; maximum: Math.min(480, metaPage.width - metaPage.rightWidth - metaPage.centerMinimum - 12)
        onResized: function(value) { metaPage.leftLive = value }
        onCommitted: function(value) { backend.setLayoutSize("meta_left", value); metaPage.leftLive = -1 }
        onReset: backend.setLayoutSize("meta_left", -1)
    }

    // ---------- Center: album fields + per-track artists ----------
    Card {
        flat: true; padding: 20
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 0; Layout.minimumWidth: 0
        ColumnLayout {
            anchors.fill: parent; spacing: 14
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 32; spacing: 8
                SectionTitle { text: win.tr("albumInfo"); Layout.fillWidth: true }
                Badge {
                    visible: metaPage.status === "applied" && !win.metaView.metaError && win.metaView.metaChosen >= 0
                    tone: "good"; text: win.tr("metaApplied")
                }
            }
            // Labels in front of their fields; the album gets a full row, the rest pair up.
            GridLayout {
                Layout.fillWidth: true; columns: 4; columnSpacing: 10; rowSpacing: 10
                Label { text: win.tr("album") }
                Field {
                    Layout.fillWidth: true; Layout.columnSpan: 3
                    text: metaPage.meta.album.album || ""
                    onEditingFinished: backend.metadata.setMeta("album.album", text)
                    Accessible.name: win.tr("album")
                }
                Label { text: win.tr("artist") }
                Field {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    text: metaPage.meta.album.artist || ""
                    onEditingFinished: backend.metadata.setMeta("album.artist", text)
                    Accessible.name: win.tr("artist")
                }
                Label { text: win.tr("fAlbumArtist"); Layout.leftMargin: 6 }
                Field {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    text: metaPage.meta.album.album_artist || ""
                    placeholderText: metaPage.meta.album.artist || ""     // empty: the artist is used
                    onEditingFinished: backend.metadata.setMeta("album.album_artist", text)
                    Accessible.name: win.tr("fAlbumArtist")
                }
                Label { text: win.tr("fDate") }
                Field {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    text: metaPage.meta.album.date || ""; placeholderText: win.tr("datePlaceholder")
                    onEditingFinished: backend.metadata.setMeta("album.date", text)
                    Accessible.name: win.tr("fDate")
                }
                Label { text: win.tr("fGenre"); Layout.leftMargin: 6 }
                Field {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    text: metaPage.meta.album.genre || ""
                    onEditingFinished: backend.metadata.setMeta("album.genre", text)
                    Accessible.name: win.tr("fGenre")
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line; Layout.topMargin: 4 }
            SectionTitle {
                text: win.tr("trackTags"); Layout.fillWidth: true
                note: win.fmt("trackTagsNote", { n: win.discView.chapterSelected || 0 })
            }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12 + tagBar.gutter; spacing: 12
                Copy { text: "#"; Layout.preferredWidth: 26; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                Copy { text: win.tr("current"); Layout.fillWidth: true; Layout.preferredWidth: 1; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                // lines up with the text inside the artist fields (their left padding)
                Copy { text: win.tr("trackArtist"); Layout.fillWidth: true; Layout.preferredWidth: 1; leftPadding: 10; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
            }
            ListView {
                id: tagList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 2; model: chapterModel
                ScrollBar.vertical: SlimScrollBar { id: tagBar }
                populate: ListEnter {}
                add: ListEnter {}
                delegate: Rectangle {
                    id: tagRow
                    required property int index
                    required property int number
                    required property string title
                    required property string artist
                    required property bool included
                    property alias artistField: artistField
                    width: ListView.view.width - tagBar.gutter; height: Theme.rowHeight; radius: 8
                    color: rowHover.hovered || artistField.activeFocus ? Theme.raised : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    HoverHandler { id: rowHover }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 12
                        // Chapters left out of the export are dimmed: their tags are not written anywhere.
                        opacity: tagRow.included ? 1 : 0.45
                        Copy { text: tagRow.number.toString().padStart(2, "0"); font.family: Theme.num; font.features: Theme.tabular; color: Theme.muted; Layout.preferredWidth: 26; wrapMode: Text.NoWrap }
                        Copy {
                            text: tagRow.title || ("Track " + tagRow.number.toString().padStart(2, "0"))
                            color: tagRow.title ? Theme.text : Theme.faint; font.pixelSize: Theme.item
                            Layout.fillWidth: true; Layout.preferredWidth: 1; wrapMode: Text.NoWrap; elide: Text.ElideRight
                        }
                        Field {
                            id: artistField
                            quiet: true; text: tagRow.artist; implicitHeight: Theme.compact ? 28 : 32
                            placeholderText: metaPage.meta.album.album_artist || metaPage.meta.album.artist || ""
                            Layout.fillWidth: true; Layout.preferredWidth: 1
                            Accessible.name: win.tr("trackArtist") + " " + tagRow.number
                            onEditingFinished: if (text !== tagRow.artist) backend.metadata.setTrackArtist(tagRow.index, text)
                            Keys.onReturnPressed: focus = false
                            Keys.onEnterPressed: focus = false
                            Keys.onEscapePressed: { text = Qt.binding(function() { return tagRow.artist }); focus = false }
                            Keys.onUpPressed: metaPage.editArtistAt(tagRow.index - 1)
                            Keys.onDownPressed: metaPage.editArtistAt(tagRow.index + 1)
                        }
                    }
                }
            }
        }
    }

    }
        ColumnLayout { id: previewSlot; Layout.fillWidth: true; Layout.fillHeight: false; spacing: 0 }  // a layout fills by default; this one is only as tall as the panel in it (0 when there is none)
    }

    Splitter {
        Layout.fillHeight: true; Layout.leftMargin: -6; Layout.rightMargin: -6; z: 1; divider: true
        size: metaPage.rightWidth; direction: -1; minimum: 300; maximum: Math.min(560, metaPage.width - metaPage.leftWidth - metaPage.centerMinimum - 12)
        onResized: function(value) { metaPage.rightLive = value }
        onCommitted: function(value) { backend.setLayoutSize("meta_right", value); metaPage.rightLive = -1 }
        onReset: backend.setLayoutSize("meta_right", -1)
    }

    // ---------- Right: online lookup, then what to apply ----------
    Card {
        flat: true; padding: 20
        Layout.preferredWidth: metaPage.rightWidth; Layout.fillHeight: true
        ColumnLayout {
            anchors.fill: parent; spacing: 16
            // The lookup takes what room is left; on a short window it is cut off at the bottom
            // rather than pushing the apply button out of sight.
            Item {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                ColumnLayout {
                    anchors.fill: parent; spacing: 16
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 10
                        SectionTitle { text: win.tr("onlineMeta"); Layout.fillWidth: true; Layout.preferredHeight: 32 }
                        // Labels in front of their fields, in one column so the fields line up (as on the review page)
                        GridLayout {
                            Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 10
                            Label { text: win.tr("sourceLabel") }
                            SourcePicker {
                                Layout.fillWidth: true; enabled: !win.appView.working
                                current: metaPage.source
                                onPicked: function(key) { metaPage.source = key }
                            }
                            Label { text: win.tr("artist") }
                            Field { id: qArtist; text: metaPage.meta.album.artist || ""; Layout.fillWidth: true; onAccepted: metaPage.searchOnline(); Accessible.name: win.tr("artist") }
                            Label { text: win.tr("album") }
                            Field { id: qAlbum; text: metaPage.meta.album.album || ""; Layout.fillWidth: true; onAccepted: metaPage.searchOnline(); Accessible.name: win.tr("album") }
                            Disclosure {
                                id: metaBarcodeToggle; Layout.columnSpan: 2
                                text: win.tr("barcodeToggle"); enabled: !win.appView.working
                                onOpenChanged: if (open) qBarcode.forceActiveFocus()
                            }
                            Label { visible: metaBarcodeToggle.open; text: win.tr("barcodeShort") }
                            Field { id: qBarcode; visible: metaBarcodeToggle.open; mono: true; Layout.fillWidth: true; placeholderText: win.tr("barcodePlaceholder"); onAccepted: metaPage.searchOnline(); Accessible.name: win.tr("barcode") }
                        }
                        ActionButton {
                            text: metaPage.status === "loading" && win.metaView.metaChosen < 0 ? win.tr("searching") : win.tr("searchMeta")
                            primary: resultList.count === 0; Layout.fillWidth: true; enabled: !win.appView.working
                            onClicked: metaPage.searchOnline()
                        }
                    }
                    SectionTitle { text: win.tr("metaResults"); note: resultList.count > 0 ? String(resultList.count) : ""; Layout.fillWidth: true }
                    Rectangle {
                        readonly property string message: metaPage.status === "loading" && resultList.count === 0 ? win.tr("searching")
                            : metaPage.status === "empty" ? win.tr("noResults")
                            : metaPage.status === "error" ? win.metaView.metaError
                            : resultList.count === 0 ? win.tr("metaIdle") : ""
                        visible: message !== ""
                        Layout.fillWidth: true; Layout.preferredHeight: statusText.implicitHeight + 18; radius: 10
                        color: metaPage.status === "error" ? "transparent" : Theme.raised
                        border.color: metaPage.status === "error" ? Theme.dangerLine : "transparent"
                        Copy {
                            id: statusText; anchors.fill: parent; anchors.margins: 9; anchors.leftMargin: 12
                            text: parent.message; font.pixelSize: Theme.px(12); lineHeight: 1.3
                            color: metaPage.status === "error" ? Theme.danger : Theme.sub
                        }
                    }
                    ListView {
                        id: resultList
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 8; model: metaModel
                        visible: count > 0
                        ScrollBar.vertical: SlimScrollBar { id: resultBar }
                        populate: ListEnter {}
                        add: ListEnter {}
                        delegate: Rectangle {
                            id: res
                            required property int index
                            required property string label
                            required property string detail
                            required property string thumb
                            required property bool chosen
                            width: ListView.view.width - resultBar.gutter; height: Math.max(resInfo.implicitHeight, 48) + 22; radius: 10
                            color: chosen ? Theme.accentSoft : resHover.hovered ? Theme.field : Theme.raised
                            border.width: chosen ? 2 : 1
                            border.color: chosen || resHover.hovered ? Theme.accent : Theme.line2
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                            HoverHandler { id: resHover }
                            Rectangle {
                                x: 12; y: 11; width: 48; height: 48; radius: 6; color: Theme.chip; clip: true
                                Image { id: thumbImage; anchors.fill: parent; source: res.thumb; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 96 }
                                Icon { anchors.centerIn: parent; width: 20; height: 20; kind: "disc"; ink: Theme.faint; visible: thumbImage.status !== Image.Ready }
                            }
                            ColumnLayout {
                                id: resInfo; x: 70; y: 11; width: parent.width - x - 12; spacing: 4
                                Copy { text: res.label; font.weight: Font.DemiBold; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                                Copy { text: res.detail; color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                            }
                            MouseArea { anchors.fill: parent; enabled: !win.appView.working; cursorShape: Qt.PointingHandCursor; onClicked: backend.metadata.metaChoose(res.index) }
                        }
                    }
                    Item { Layout.fillHeight: true; visible: resultList.count === 0 }
                    Copy { text: win.tr("metaPrivacy"); color: Theme.faint; font.pixelSize: Theme.px(11); Layout.fillWidth: true; lineHeight: 1.3 }
                }
            }

            // Footer: what to take from the chosen result, and apply it
            ColumnLayout {
                Layout.fillWidth: true; spacing: 8
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line; Layout.bottomMargin: 4 }
                Label { text: win.tr("applyWhat") }
                Flow {
                    Layout.fillWidth: true; spacing: 14
                    Repeater {
                        model: [{ key: "applyAlbum", label: win.tr("applyAlbum") }, { key: "applyCover", label: win.tr("applyCover") },
                                { key: "applyArtists", label: win.tr("applyArtists") }, { key: "applyTitles", label: win.tr("applyTitles") }]
                        AbstractButton {
                            id: opt
                            required property var modelData
                            readonly property bool on: metaPage[modelData.key]
                            implicitWidth: optRow.implicitWidth; implicitHeight: 26
                            checkable: true; checked: on
                            Accessible.name: modelData.label
                            onClicked: metaPage[modelData.key] = !metaPage[modelData.key]
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            contentItem: Item {}
                            background: RowLayout {
                                id: optRow; spacing: 6
                                SelectionMark { checked: opt.on }
                                Copy { text: opt.modelData.label; wrapMode: Text.NoWrap; color: opt.on ? Theme.text : Theme.sub }
                            }
                        }
                    }
                }
                Copy {
                    visible: metaPage.status === "applied" && !!win.metaView.metaError
                    text: win.tr("metaApplied") + " · " + win.metaView.metaError
                    color: Theme.danger; font.pixelSize: Theme.px(12); Layout.fillWidth: true
                }
                ActionButton {
                    text: metaPage.status === "loading" && win.metaView.metaChosen >= 0 ? win.tr("metaApplying")
                        : win.metaView.metaChosen >= 0 ? win.tr("applyChosen") : win.tr("pickResult")
                    primary: true; large: true; Layout.fillWidth: true; Layout.topMargin: 4
                    enabled: !win.appView.working && win.metaView.metaChosen >= 0 && metaPage.anyApply
                    onClicked: backend.metadata.metaApply(metaPage.applyAlbum, metaPage.applyCover, metaPage.applyArtists, metaPage.applyTitles)
                }
            }
        }
    }
}
