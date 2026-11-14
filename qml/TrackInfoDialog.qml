import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
// Details sheet for one audio or subtitle track.
Popup {
    id: dialog
    required property var win
    readonly property var info: win.discView.trackInfo || ({ sections: [] })
    property bool copied: false
    parent: win.contentItem
    anchors.centerIn: parent
    width: Math.min(560, parent.width - 48)
    height: Math.min(content.implicitHeight + 48, parent.height - 80)
    padding: 24; modal: true; focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onOpened: copied = false
    background: Rectangle { color: Theme.panel; radius: 14; border.color: Theme.line2 }
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, Theme.light ? 0.25 : 0.5) }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: Theme.animate ? 0.96 : 1; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

    ColumnLayout {
        id: content
        anchors.fill: parent; spacing: 14
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Copy { text: dialog.info.title; font.pixelSize: Theme.px(20); font.bold: true }
            Copy { text: dialog.info.heading; color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
        }
        ScrollView {
            id: scroller
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.preferredHeight: sheet.implicitHeight
            clip: true; contentWidth: availableWidth
            rightPadding: sheetBar.gutter
            ScrollBar.vertical: SlimScrollBar { id: sheetBar; parent: scroller; x: scroller.mirrored ? 0 : scroller.width - width; y: scroller.topPadding; height: scroller.availableHeight }
            ColumnLayout {
                id: sheet
                width: scroller.availableWidth; spacing: 14
                Repeater {
                    model: dialog.info.sections
                    ColumnLayout {
                        id: section
                        required property var modelData
                        Layout.fillWidth: true; spacing: 6
                        Copy { text: section.modelData.title; font.pixelSize: Theme.px(12); font.weight: Font.DemiBold; color: Theme.muted }
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: rows.implicitHeight + 8
                            radius: 10; color: Theme.raised; border.color: Theme.line
                            ColumnLayout {
                                id: rows
                                x: 14; y: 4; width: parent.width - 28; spacing: 0
                                Repeater {
                                    model: section.modelData.rows
                                    Item {
                                        id: line
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true; implicitHeight: Math.max(34, value.implicitHeight + 14)
                                        Rectangle { visible: line.index > 0; width: parent.width; height: 1; color: Theme.line }
                                        RowLayout {
                                            anchors.fill: parent; spacing: 12
                                            Copy { text: line.modelData.label; color: Theme.muted; font.pixelSize: Theme.px(13); Layout.preferredWidth: 120; wrapMode: Text.NoWrap }
                                            TextEdit {
                                                id: value
                                                text: line.modelData.value; readOnly: true; selectByMouse: true
                                                color: Theme.text; selectionColor: Theme.accent; selectedTextColor: Theme.accentInk
                                                font.family: Theme.ui; font.pixelSize: Theme.px(13)
                                                wrapMode: TextEdit.Wrap; Layout.fillWidth: true
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Copy {
                    visible: dialog.info.probing || dialog.info.error !== ""
                    text: dialog.info.probing ? win.tr("tiProbing") : win.fmt("tiProbeFailed", { e: dialog.info.error })
                    color: dialog.info.probing ? Theme.muted : Theme.danger; font.pixelSize: Theme.px(12); Layout.fillWidth: true
                    opacity: dialog.info.probing ? pulse.value : 1
                    QtObject { id: pulse; property real value: 1 }
                    SequentialAnimation {
                        running: dialog.info.probing && Theme.animate && dialog.visible; loops: Animation.Infinite
                        NumberAnimation { target: pulse; property: "value"; from: 1; to: 0.45; duration: 600 }
                        NumberAnimation { target: pulse; property: "value"; from: 0.45; to: 1; duration: 600 }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            ActionButton {
                text: dialog.copied ? win.tr("tiCopied") : win.tr("tiCopy")
                enabled: dialog.info.sections.length > 0
                onClicked: dialog.copied = backend.disc.copyTrackInfo()
            }
            Item { Layout.fillWidth: true }
            ActionButton { text: win.tr("tiClose"); primary: true; onClicked: dialog.close() }
        }
    }
}
