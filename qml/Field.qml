import QtQuick
import QtQuick.Controls
TextField {
    id: field
    property bool mono: false
    property bool quiet: false   // borderless until hovered or focused (table cells)
    property bool releaseOnOutsideClick: quiet   // a click elsewhere ends editing (gui/focus.py)
    property color textColor: Theme.text
    // A text field never elides, so a long value would be cut mid-letter. While it is not being
    // edited and does not fit, the same text is drawn ending in "…" in its place.
    readonly property bool elided: !activeFocus && text !== "" && idleText.implicitWidth > width + 0.5   // implicitWidth includes the padding
    implicitHeight: Math.round(34 * Math.max(1, Theme.fontScale)); color: elided ? "transparent" : textColor; placeholderTextColor: Theme.faint
    selectionColor: Theme.accent; selectedTextColor: Theme.accentInk
    font.family: mono ? Theme.mono : Theme.ui; font.pixelSize: Theme.px(mono ? 12 : 13)
    leftPadding: 10; rightPadding: 10; selectByMouse: true
    HoverHandler { id: hover }
    Text {
        id: idleText
        visible: field.elided
        anchors.fill: parent; leftPadding: field.leftPadding; rightPadding: field.rightPadding
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        text: field.text; font: field.font; color: field.textColor; textFormat: Text.PlainText
    }
    ContextMenu.menu: EditMenu { target: field }
    onTextChanged: if (!activeFocus) cursorPosition = 0
    onActiveFocusChanged: if (!activeFocus) cursorPosition = 0
    Component.onCompleted: cursorPosition = 0
    background: Rectangle {
        radius: 8
        color: field.quiet && !field.activeFocus && !hover.hovered ? Theme.clear(Theme.field) : Theme.field
        border.color: field.activeFocus ? Theme.accent : (field.quiet && !hover.hovered ? Theme.clear(Theme.line2) : Theme.line2)
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    }
}
