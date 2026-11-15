import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
// Menu row matching the app: soft hover fill, accent check mark for the current choice.
MenuItem {
    id: item
    implicitHeight: Math.round(34 * Math.max(1, Theme.fontScale))
    implicitWidth: row.implicitWidth + leftPadding + rightPadding
    leftPadding: 10; rightPadding: 14; topPadding: 0; bottomPadding: 0
    font.family: Theme.ui; font.pixelSize: Theme.px(13)
    indicator: null
    arrow: null
    contentItem: RowLayout {
        id: row
        spacing: 8
        Item {
            visible: item.checkable
            Layout.preferredWidth: 16; Layout.preferredHeight: 16
            Icon { anchors.fill: parent; kind: "check"; ink: Theme.accentText; visible: item.checked }
        }
        Text {
            text: item.text; font: item.font; Layout.fillWidth: true
            color: !item.enabled ? Theme.faint : item.checked ? Theme.accentText : Theme.text
            elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
        }
    }
    background: Rectangle {
        implicitHeight: item.implicitHeight
        radius: 6
        color: item.highlighted ? Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, Theme.light ? 0.07 : 0.09) : Theme.clear(Theme.text)
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
}
