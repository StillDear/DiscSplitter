import QtQuick

Rectangle {
    id: mark
    property bool checked: false
    implicitWidth: 18
    implicitHeight: 18
    radius: 5
    color: checked ? Theme.accent : Theme.clear(Theme.accent)
    border.color: checked ? Theme.accent : Theme.muted
    border.width: 1
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    Icon {
        anchors.fill: parent
        anchors.margins: 2
        kind: "check"
        ink: Theme.accentInk
        opacity: mark.checked ? 1 : 0
        scale: mark.checked ? 1 : 0.4
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
    }
}
