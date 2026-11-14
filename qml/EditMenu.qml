import QtQuick
import QtQuick.Controls
// Themed, translated right-click menu for text fields (replaces Qt's built-in English one).
AppMenu {
    id: menu
    required property Item target
    readonly property bool editable: !target.readOnly
    readonly property bool hasSelection: target.selectedText.length > 0
    minWidth: 180
    AppMenuItem { text: backend.texts.editUndo; enabled: menu.editable && menu.target.canUndo; onTriggered: menu.target.undo() }
    AppMenuItem { text: backend.texts.editRedo; enabled: menu.editable && menu.target.canRedo; onTriggered: menu.target.redo() }
    MenuSeparator {
        topPadding: 4; bottomPadding: 4
        contentItem: Rectangle { implicitHeight: 1; color: Theme.line }
    }
    AppMenuItem { text: backend.texts.editCut; enabled: menu.editable && menu.hasSelection; onTriggered: menu.target.cut() }
    AppMenuItem { text: backend.texts.editCopy; enabled: menu.hasSelection; onTriggered: menu.target.copy() }
    AppMenuItem { text: backend.texts.editPaste; enabled: menu.editable && menu.target.canPaste; onTriggered: menu.target.paste() }
    AppMenuItem { text: backend.texts.editDelete; enabled: menu.editable && menu.hasSelection; onTriggered: menu.target.remove(menu.target.selectionStart, menu.target.selectionEnd) }
    MenuSeparator {
        topPadding: 4; bottomPadding: 4
        contentItem: Rectangle { implicitHeight: 1; color: Theme.line }
    }
    AppMenuItem { text: backend.texts.editSelectAll; enabled: menu.target.length > 0; onTriggered: menu.target.selectAll() }
}
