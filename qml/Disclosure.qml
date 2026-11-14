import QtQuick
import QtQuick.Controls
// A small "Show more ⌄" text toggle for folding an optional field away.
AbstractButton {
    id: control
    property bool open: false
    implicitHeight: 24; implicitWidth: row.implicitWidth
    hoverEnabled: true
    Accessible.name: text
    onClicked: open = !open
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    contentItem: Item {
        Row {
            id: row
            spacing: 4; anchors.verticalCenter: parent.verticalCenter
            Copy {
                text: control.text; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
                color: control.hovered ? Theme.text : Theme.muted; anchors.verticalCenter: parent.verticalCenter
            }
            Icon {
                kind: "down"; width: 12; height: 12; ink: control.hovered ? Theme.text : Theme.muted
                anchors.verticalCenter: parent.verticalCenter
                rotation: control.open ? 180 : 0
                Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
            }
        }
    }
    background: Item {}
}
