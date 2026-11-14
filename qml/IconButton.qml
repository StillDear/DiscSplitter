import QtQuick
import QtQuick.Controls
Button {
    id: control
    property string iconKind: "gear"
    property color ink: hovered ? Theme.text : Theme.muted
    implicitWidth: 36; implicitHeight: 32; padding: 0
    opacity: enabled ? 1 : 0.45
    contentItem: Item {
        Icon { anchors.centerIn: parent; width: 16; height: 16; kind: control.iconKind; ink: control.ink }
    }
    background: Rectangle { radius: 8; color: control.hovered ? Theme.raised : "transparent"; border.color: control.visualFocus ? Theme.accent : "transparent" }
}
