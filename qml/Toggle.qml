import QtQuick
Rectangle {
    property bool checked: true
    implicitWidth: 38; implicitHeight: 22; radius: 11
    color: checked ? Theme.accent : Theme.line2
    Behavior on color { ColorAnimation { duration: Theme.normal } }
    Rectangle {
        width: 16; height: 16; radius: 8; anchors.verticalCenter: parent.verticalCenter
        x: parent.checked ? parent.width - width - 3 : 3
        color: parent.checked ? Theme.accentInk : Theme.panel
        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    }
}
