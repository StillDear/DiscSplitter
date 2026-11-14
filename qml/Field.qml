import QtQuick
import QtQuick.Controls
TextField {
    id: field
    property bool mono: false
    property bool quiet: false   // borderless until hovered or focused (table cells)
    property bool releaseOnOutsideClick: quiet   // a click elsewhere ends editing (gui/focus.py)
    implicitHeight: Math.round(34 * Math.max(1, Theme.fontScale)); color: Theme.text; placeholderTextColor: Theme.faint
    selectionColor: Theme.accent; selectedTextColor: Theme.accentInk
    font.family: mono ? Theme.mono : Theme.ui; font.pixelSize: Theme.px(mono ? 12 : 13)
    leftPadding: 10; rightPadding: 10; selectByMouse: true
    HoverHandler { id: hover }
    ContextMenu.menu: EditMenu { target: field }
    onTextChanged: if (!activeFocus) cursorPosition = 0
    onActiveFocusChanged: if (!activeFocus) cursorPosition = 0
    Component.onCompleted: cursorPosition = 0
    background: Rectangle {
        radius: 8
        color: field.quiet && !field.activeFocus && !hover.hovered ? "transparent" : Theme.field
        border.color: field.activeFocus ? Theme.accent : (field.quiet && !hover.hovered ? "transparent" : Theme.line2)
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    }
}
