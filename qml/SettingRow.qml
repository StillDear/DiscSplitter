import QtQuick
import QtQuick.Layouts
// One row inside a SettingGroup: title + hint on the left, controls on the right.
Rectangle {
    id: rowRoot
    property alias title: titleText.text
    property alias hint: hintText.text
    property bool first: false
    property bool tinted: false
    default property alias controls: slot.data
    Layout.fillWidth: true
    implicitHeight: Math.max(54, info.implicitHeight + 20)
    color: tinted ? Theme.accentSoft : "transparent"
    Rectangle { visible: !rowRoot.first; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 1; color: Theme.line2 }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 12
        ColumnLayout {
            id: info; Layout.fillWidth: true; spacing: 3
            Copy { id: titleText; Layout.fillWidth: true }
            Copy { id: hintText; visible: text !== ""; color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true }
        }
        RowLayout { id: slot; spacing: 8 }
    }
}
