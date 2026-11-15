import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Item {
    id: startPage
    required property var win
    // Everything sits above the tool status line; when the preview bar leaves little room the drop zone gives way first.
    readonly property real room: statusLine.y - 12
    readonly property real fixedHeight: (win.exportView.resume && !win.appView.pipeline ? 96 + 16 : 0) + (win.discView.source !== "" ? 52 + 16 : 0)
    readonly property real dropHeight: Math.max(190, Math.min(330, room - fixedHeight))
    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(780, parent.width - 24); spacing: 16
        y: Math.max(0, (startPage.room - height) / 2)

        // Unfinished job
        Rectangle {
            visible: win.exportView.resume && !win.appView.pipeline
            Layout.fillWidth: true; Layout.preferredHeight: 96; radius: 14
            color: Theme.accentSoft; border.color: Theme.accent
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 16
                Icon { kind: "refresh"; ink: Theme.accentText; Layout.preferredWidth: 22; Layout.preferredHeight: 22 }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Copy { text: win.tr("resumeTitle"); font.pixelSize: Theme.px(12); color: Theme.accentText }
                    Copy { text: win.exportView.resumeText; font.pixelSize: Theme.px(15); font.bold: true; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideMiddle }
                    Copy { text: win.tr("resumeHint"); font.pixelSize: Theme.px(12); color: Theme.sub; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                }
                ActionButton { text: win.tr("discard"); enabled: !win.appView.working; onClicked: backend.exporter.requestDiscard() }
                ActionButton { text: win.tr("resume"); primary: true; enabled: !win.appView.working; onClicked: backend.exporter.resume() }
            }
        }

        // Drop zone
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: startPage.dropHeight; radius: 14; color: Theme.panel; border.color: Theme.line
            DropArea {
                id: drop; anchors.fill: parent
                onDropped: function(event) { if (event.hasUrls) backend.disc.setSource(event.urls[0].toString()) }
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: 6; radius: 10; color: drop.containsDrag ? Theme.accentSoft : "transparent"
                Behavior on color { ColorAnimation { duration: Theme.normal } }
                Behavior on border.color { ColorAnimation { duration: Theme.normal } }
                border.color: drop.containsDrag ? Theme.accent : Theme.line2; border.width: 1
                ColumnLayout {
                    anchors.centerIn: parent; width: parent.width - 80; spacing: 14
                    Icon {
                        id: dropDisc
                        visible: startPage.dropHeight >= 270
                        kind: "disc"; ink: drop.containsDrag ? Theme.accent : Theme.muted
                        Layout.preferredWidth: 56; Layout.preferredHeight: 56; Layout.alignment: Qt.AlignHCenter
                        scale: drop.containsDrag ? 1.12 : 1
                        Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
                        RotationAnimation on rotation {
                            running: Theme.animate && (drop.containsDrag || (win.appView.working && !win.appView.pipeline))
                            from: 0; to: 360; duration: 1600; loops: Animation.Infinite
                            onRunningChanged: if (!running) dropDisc.rotation = 0
                        }
                    }
                    Copy { text: win.tr("startTitle"); font.pixelSize: Theme.px(20); font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                    Copy { text: win.tr("startHint"); color: Theme.muted; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; lineHeight: 1.3 }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 6; spacing: 8
                        Field { id: pathField; mono: true; Layout.preferredWidth: 360; placeholderText: "E:/Blurays/…"; enabled: !win.appView.working; onAccepted: backend.disc.setSource(text) }
                        ActionButton { text: win.tr("chooseFolder"); large: true; implicitHeight: 34; enabled: !win.appView.working; onClicked: win.openFolder("source") }
                        ActionButton { text: win.tr("chooseSourceFile"); large: true; implicitHeight: 34; enabled: !win.appView.working; onClicked: win.openSourceFile() }
                    }
                }
            }
        }

        // Last used
        Rectangle {
            visible: win.discView.source !== ""
            Layout.fillWidth: true; Layout.preferredHeight: 52; radius: 14; color: Theme.panel; border.color: Theme.line
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 10; spacing: 12
                Icon { kind: "folder"; ink: Theme.muted; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                Copy { text: win.tr("recent"); color: Theme.muted; wrapMode: Text.NoWrap }
                Copy { text: win.discView.source; font.family: Theme.mono; font.pixelSize: Theme.px(12); Layout.fillWidth: true; elide: Text.ElideMiddle; wrapMode: Text.NoWrap }
                ActionButton { text: win.tr("reopen"); ghost: true; enabled: !win.appView.working; onClicked: backend.disc.scan() }
            }
        }
    }

    // Status line
    RowLayout {
        id: statusLine
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 20
        Repeater {
            model: toolModel
            RowLayout {
                required property string tool
                required property bool available
                spacing: 7
                Rectangle { Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4; color: available ? Theme.good : "transparent"; border.color: available ? Theme.good : Theme.danger }
                Copy { text: tool; font.pixelSize: Theme.px(12); color: available ? Theme.muted : Theme.danger; wrapMode: Text.NoWrap }
            }
        }
        Item { Layout.fillWidth: true }
    }
}
