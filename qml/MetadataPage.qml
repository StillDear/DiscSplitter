import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
RowLayout {
    id: metaPage
    required property var win
    readonly property var meta: win.metaView.meta || ({ album: {}, audio: {}, track_artists: {}, cover: "" })
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
    readonly property real rightWidth: rightLive > 0 ? rightLive : fit(layoutSizes.meta_right || 340, 0.36)
    function searchOnline() {
        if (!win.appView.busy)
            backend.metadata.metaSearch(source, qArtist.text, qAlbum.text, metaBarcodeToggle.open ? qBarcode.text : "")
    }
    spacing: 12

    FileDialog {
        id: coverDialog
        title: win.tr("cover")
        nameFilters: [win.tr("imageFilter")]
        onAccepted: backend.metadata.chooseCover(selectedFile.toString())
    }
    CoverCropDialog { id: cropDialog; objectName: "coverCrop"; win: metaPage.win }

    // ---------- Left: cover ----------
    Card {
        Layout.preferredWidth: metaPage.leftWidth; Layout.fillHeight: true
        ColumnLayout {
            anchors.fill: parent; spacing: 14
            SectionTitle { text: win.tr("cover"); Layout.fillWidth: true }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: width; radius: 10
                color: Theme.raised; border.color: Theme.line2; clip: true
                Image {
                    id: coverImage
                    anchors.fill: parent; anchors.margins: 1
                    source: metaPage.coverUrl; fillMode: Image.PreserveAspectFit
                    asynchronous: true; cache: false; sourceSize.width: 600
                    opacity: status === Image.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                }
                ColumnLayout {
                    anchors.centerIn: parent; spacing: 8; visible: coverImage.status !== Image.Ready
                    Icon { kind: "disc"; ink: Theme.faint; Layout.preferredWidth: 44; Layout.preferredHeight: 44; Layout.alignment: Qt.AlignHCenter }
                    Copy { text: win.tr("noCover"); color: Theme.faint; Layout.alignment: Qt.AlignHCenter }
                }
                DropArea {
                    anchors.fill: parent
                    onDropped: function(event) { if (event.hasUrls) backend.metadata.chooseCover(event.urls[0].toString()) }
                }
            }
            RowLayout {
                spacing: 8
                ActionButton { text: win.tr("chooseCover"); Layout.fillWidth: true; onClicked: coverDialog.open() }
                ActionButton { text: win.tr("removeCover"); ghost: true; enabled: !!metaPage.meta.cover; onClicked: backend.metadata.clearCover() }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                ActionButton { text: win.tr("cropCover"); Layout.fillWidth: true; enabled: !!metaPage.meta.cover && !win.appView.busy; onClicked: cropDialog.showCover() }
                ActionButton { text: win.tr("cropRestore"); ghost: true; visible: !!win.metaView.canRestoreCover; enabled: !win.appView.busy; onClicked: backend.metadata.restoreCover() }
            }
            Copy { text: win.tr("coverHint"); color: Theme.faint; font.pixelSize: Theme.px(12); Layout.fillWidth: true; lineHeight: 1.3 }

            Item { Layout.fillHeight: true }
        }
    }

    Splitter {
        Layout.fillHeight: true; Layout.leftMargin: -12; Layout.rightMargin: -12
        size: metaPage.leftWidth; direction: 1; minimum: 220; maximum: Math.min(480, metaPage.width - metaPage.rightWidth - metaPage.centerMinimum - 24)
        onResized: function(value) { metaPage.leftLive = value }
        onCommitted: function(value) { backend.setLayoutSize("meta_left", value); metaPage.leftLive = -1 }
        onReset: backend.setLayoutSize("meta_left", -1)
    }
    // ---------- Center: album fields + per-track artists ----------
    Card {
        Layout.fillWidth: true; Layout.fillHeight: true; padding: 20
        ColumnLayout {
            anchors.fill: parent; spacing: 14
            Copy { text: win.tr("albumInfo"); font.pixelSize: Theme.px(20); font.bold: true }
            GridLayout {
                Layout.fillWidth: true; columns: 2; columnSpacing: 12; rowSpacing: 10
                Repeater {
                    model: [{ key: "artist", label: win.tr("artist") }, { key: "album_artist", label: win.tr("fAlbumArtist") },
                            { key: "album", label: win.tr("album") }, { key: "date", label: win.tr("fDate") },
                            { key: "genre", label: win.tr("fGenre") }]
                    ColumnLayout {
                        id: fieldBox
                        required property var modelData
                        spacing: 4; Layout.fillWidth: true; Layout.preferredWidth: 1
                        Copy { text: fieldBox.modelData.label; font.pixelSize: Theme.px(12); color: Theme.muted }
                        Field {
                            Layout.fillWidth: true
                            text: metaPage.meta.album[fieldBox.modelData.key] || ""
                            onEditingFinished: backend.metadata.setMeta("album." + fieldBox.modelData.key, text)
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true; Layout.topMargin: 6
                SectionTitle { text: win.tr("trackTags"); note: win.tr("trackArtistHint"); Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12 + tagBar.gutter; spacing: 12
                Copy { text: "#"; Layout.preferredWidth: 26; color: Theme.faint; font.pixelSize: Theme.px(12) }
                Copy { text: win.tr("current"); Layout.fillWidth: true; Layout.preferredWidth: 1; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                Copy { text: win.tr("trackArtist"); Layout.fillWidth: true; Layout.preferredWidth: 1; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
            }
            ListView {
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
                    width: ListView.view.width - tagBar.gutter; height: Theme.rowHeight; radius: 8
                    color: rowHover.hovered ? Theme.raised : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    HoverHandler { id: rowHover }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 12
                        Copy { text: tagRow.number.toString().padStart(2, "0"); font.family: Theme.mono; color: Theme.muted; Layout.preferredWidth: 26; wrapMode: Text.NoWrap }
                        Copy { text: tagRow.title || ("Track " + tagRow.number.toString().padStart(2, "0")); color: tagRow.title ? Theme.text : Theme.faint; font.pixelSize: Theme.px(14); Layout.fillWidth: true; Layout.preferredWidth: 1; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                        Field {
                            quiet: true; text: tagRow.artist; implicitHeight: Theme.compact ? 28 : 32
                            placeholderText: metaPage.meta.album.album_artist || metaPage.meta.album.artist || ""
                            Layout.fillWidth: true; Layout.preferredWidth: 1
                            onEditingFinished: if (text !== tagRow.artist) backend.metadata.setTrackArtist(tagRow.index, text)
                        }
                    }
                }
            }
        }
    }

    Splitter {
        Layout.fillHeight: true; Layout.leftMargin: -12; Layout.rightMargin: -12
        size: metaPage.rightWidth; direction: -1; minimum: 280; maximum: Math.min(560, metaPage.width - metaPage.leftWidth - metaPage.centerMinimum - 24)
        onResized: function(value) { metaPage.rightLive = value }
        onCommitted: function(value) { backend.setLayoutSize("meta_right", value); metaPage.rightLive = -1 }
        onReset: backend.setLayoutSize("meta_right", -1)
    }
    // ---------- Right: online lookup ----------
    Card {
        Layout.preferredWidth: metaPage.rightWidth; Layout.fillHeight: true
        ColumnLayout {
            anchors.fill: parent; spacing: 12
            SectionTitle { text: win.tr("onlineMeta"); Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                Copy { text: win.tr("sourceLabel"); color: Theme.muted; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                SourcePicker {
                    Layout.fillWidth: true
                    current: metaPage.source
                    onPicked: function(key) { metaPage.source = key }
                }
            }
            ColumnLayout { spacing: 4; Layout.fillWidth: true
                Copy { text: win.tr("artist"); font.pixelSize: Theme.px(12); color: Theme.muted }
                Field { id: qArtist; text: metaPage.meta.album.artist || ""; Layout.fillWidth: true; onAccepted: metaPage.searchOnline() }
            }
            ColumnLayout { spacing: 4; Layout.fillWidth: true
                Copy { text: win.tr("album"); font.pixelSize: Theme.px(12); color: Theme.muted }
                Field { id: qAlbum; text: metaPage.meta.album.album || ""; Layout.fillWidth: true; onAccepted: metaPage.searchOnline() }
            }
            Disclosure {
                id: metaBarcodeToggle
                text: win.tr("barcodeToggle")
                onOpenChanged: if (open) qBarcode.forceActiveFocus()
            }
            ColumnLayout { spacing: 4; Layout.fillWidth: true; visible: metaBarcodeToggle.open
                Copy { text: win.tr("barcode"); font.pixelSize: Theme.px(12); color: Theme.muted; Layout.fillWidth: true }
                Field { id: qBarcode; mono: true; Layout.fillWidth: true; onAccepted: metaPage.searchOnline() }
            }
            ActionButton {
                text: win.metaView.metaStatus === "loading" ? win.tr("searching") : win.tr("searchMeta")
                Layout.fillWidth: true; enabled: !win.appView.busy
                onClicked: metaPage.searchOnline()
            }
            ListView {
                id: resultList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 6; model: metaModel
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
                    width: ListView.view.width - resultBar.gutter; height: resRow.implicitHeight + 16; radius: 10
                    color: chosen ? Theme.accentSoft : (resHover.hovered ? Theme.raised : "transparent")
                    border.color: chosen ? Theme.accent : (resHover.hovered ? Theme.line2 : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    HoverHandler { id: resHover }
                    RowLayout {
                        id: resRow; x: 8; y: 8; width: parent.width - 16; spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 6; color: Theme.raised; clip: true
                            Image { id: thumbImage; anchors.fill: parent; source: res.thumb; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 88 }
                            Icon { anchors.centerIn: parent; width: 20; height: 20; kind: "disc"; ink: Theme.faint; visible: thumbImage.status !== Image.Ready }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Copy { text: res.label; font.weight: Font.DemiBold; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                            Copy { text: res.detail; color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                        }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: backend.metadata.metaChoose(res.index) }
                }
                Copy {
                    anchors.centerIn: parent; width: parent.width - 20; horizontalAlignment: Text.AlignHCenter
                    visible: resultList.count === 0 && (win.metaView.metaStatus === "empty" || win.metaView.metaStatus === "error")
                    text: win.metaView.metaStatus === "error" ? win.metaView.metaError : win.tr("noResults")
                    color: win.metaView.metaStatus === "error" ? Theme.danger : Theme.faint
                }
            }

            // What to apply
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Copy { text: win.tr("applyWhat"); font.pixelSize: Theme.px(12); color: Theme.muted }
                Flow {
                    Layout.fillWidth: true; spacing: 14
                    Repeater {
                        model: [{ key: "applyAlbum", label: win.tr("applyAlbum") }, { key: "applyCover", label: win.tr("applyCover") },
                                { key: "applyArtists", label: win.tr("applyArtists") }, { key: "applyTitles", label: win.tr("applyTitles") }]
                        Item {
                            id: opt
                            required property var modelData
                            implicitWidth: optRow.implicitWidth; implicitHeight: 26
                            RowLayout {
                                id: optRow; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                                SelectionMark { checked: metaPage[opt.modelData.key] }
                                Copy { text: opt.modelData.label; wrapMode: Text.NoWrap }
                            }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: metaPage[opt.modelData.key] = !metaPage[opt.modelData.key] }
                        }
                    }
                }
            }
            ActionButton {
                text: win.metaView.metaChosen >= 0 ? win.tr("applyChosen") : win.tr("pickResult")
                primary: win.metaView.metaChosen >= 0; Layout.fillWidth: true
                enabled: !win.appView.busy && win.metaView.metaChosen >= 0 && (metaPage.applyAlbum || metaPage.applyCover || metaPage.applyArtists || metaPage.applyTitles)
                onClicked: backend.metadata.metaApply(metaPage.applyAlbum, metaPage.applyCover, metaPage.applyArtists, metaPage.applyTitles)
            }
            Copy {
                visible: win.metaView.metaStatus === "applied"
                text: win.tr("metaApplied") + (win.metaView.metaError ? " · " + win.metaView.metaError : "")
                color: win.metaView.metaError ? Theme.danger : Theme.goodText; font.pixelSize: Theme.px(12); Layout.fillWidth: true
            }
            Copy { text: win.tr("metaPrivacy"); color: Theme.faint; font.pixelSize: Theme.px(11); Layout.fillWidth: true }
        }
    }
}
