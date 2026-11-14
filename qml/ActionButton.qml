import QtQuick
import QtQuick.Controls
Button {
    id: control
    property bool primary: false
    property bool selected: false
    property bool danger: false
    property bool ghost: false
    property bool large: false
    implicitHeight: Math.round((large ? 40 : 32) * Math.max(1, Theme.fontScale))
    implicitWidth: Math.max(large ? 120 : 64, contentItem.implicitWidth + (large ? 44 : 26))
    font.pixelSize: Theme.px(large ? 14 : 13); font.family: Theme.ui; font.bold: primary
    padding: 0
    opacity: enabled ? 1 : 0.45
    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    contentItem: Text {
        text: control.text; font: control.font
        color: control.primary ? Theme.accentInk : control.danger ? Theme.danger : control.selected ? Theme.accentText : Theme.text
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    background: Rectangle {
        radius: control.large ? 10 : 8
        color: control.primary ? (control.down ? Qt.darker(Theme.accent, 1.12) : control.hovered ? Qt.lighter(Theme.accent, 1.08) : Theme.accent)
             : control.selected ? Theme.accentSoft
             : control.ghost ? (control.hovered ? Theme.raised : "transparent")
             : control.danger ? "transparent"
             : (control.down ? Theme.segOn : control.hovered ? Qt.lighter(Theme.raised, Theme.light ? 0.97 : 1.18) : Theme.raised)
        border.color: control.visualFocus ? Theme.accent
             : control.primary || control.ghost ? "transparent"
             : control.selected ? Theme.accent
             : control.danger ? Theme.dangerLine : Theme.line2
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    }
}
