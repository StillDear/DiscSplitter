import QtQuick
import QtQuick.Layouts
SettingRow {
    id: toolRow
    required property int index
    required property string tool
    required property string path
    required property bool available
    required property bool builtin     // the Blu-ray engine shipped with the app: nothing to locate
    required property bool optional    // MKVToolNix once the engine is there: only MKV output needs it
    required property var win
    first: index === 0
    tinted: !available
    title: builtin ? tool + " · " + win.tr("builtinEngine") : tool
    hint: !available ? win.tr(builtin ? "engineMissing" : optional ? "optionalTool" : "missing")
                     : (path === tool || path === tool + ".exe" ? "PATH" : win.nativePath(path))
    implicitHeight: 56
    Copy { text: win.tr(toolRow.available ? "found" : "missing"); color: toolRow.available ? Theme.goodText : toolRow.optional ? Theme.muted : Theme.danger; wrapMode: Text.NoWrap; font.pixelSize: Theme.px(12)}
    ActionButton { text: win.tr("download"); visible: !toolRow.available && !toolRow.builtin; implicitHeight: 28; onClicked: backend.downloadTool(toolRow.tool) }
    // The built-in engine has nothing to browse for: its button stays, greyed out, so every row looks alike.
    ActionButton {
        text: win.tr("browse"); primary: !toolRow.available && !toolRow.optional; implicitHeight: 28
        enabled: !toolRow.builtin && !win.appView.working
        onClicked: win.browseTool(toolRow.tool)
    }
}
