import QtQuick
import QtQuick.Layouts
SettingRow {
    id: toolRow
    required property int index
    required property string tool
    required property string path
    required property bool available
    required property var win
    first: index === 0
    tinted: !available
    title: tool
    hint: !available ? win.tr("missing") : (path === tool || path === tool + ".exe" ? "PATH" : path)
    implicitHeight: 56
    Copy { text: win.tr(toolRow.available ? "found" : "missing"); color: toolRow.available ? Theme.goodText : Theme.danger; wrapMode: Text.NoWrap; font.pixelSize: Theme.px(12)}
    ActionButton { text: win.tr("download"); visible: !toolRow.available; implicitHeight: 28; onClicked: backend.downloadTool(toolRow.tool) }
    ActionButton { text: win.tr("browse"); primary: !toolRow.available; implicitHeight: 28; enabled: !win.appView.busy; onClicked: win.browseTool(toolRow.tool) }
}
