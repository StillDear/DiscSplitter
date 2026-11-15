import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
// Segmented control with a sliding highlight. `options` is a list of {key, label} with an optional `hint`,
// shown when that option is hovered; `current` may be "" for an action bar (no highlight).
Rectangle {
    id: seg
    property var options: []
    property string current: ""
    property bool fill: false
    property int itemHeight: Math.round(28 * Math.max(1, Theme.fontScale))
    signal picked(string key)
    readonly property int currentIndex: {
        for (let i = 0; i < options.length; i++) if (options[i].key === current) return i
        return -1
    }
    readonly property Item currentItem: currentIndex >= 0 && rep.count > currentIndex ? rep.itemAt(currentIndex) : null
    implicitHeight: itemHeight + 6
    implicitWidth: row.implicitWidth + 6
    radius: 9; color: Theme.deep; border.color: Theme.line
    opacity: enabled ? 1 : 0.5

    Rectangle {
        id: indicator
        visible: seg.currentItem !== null
        x: seg.currentItem ? row.x + seg.currentItem.x : 0
        y: row.y; height: seg.itemHeight
        width: seg.currentItem ? seg.currentItem.width : 0
        radius: 6; color: Theme.segOn; border.color: Theme.light ? Theme.line : "transparent"
        Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
    }
    RowLayout {
        id: row
        anchors.fill: parent; anchors.margins: 3; spacing: 2
        Repeater {
            id: rep
            model: seg.options
            Rectangle {
                id: opt
                required property var modelData
                readonly property bool on: seg.current === modelData.key
                Layout.fillWidth: seg.fill; Layout.preferredHeight: seg.itemHeight
                implicitWidth: label.implicitWidth + 24
                radius: 6
                color: !on && area.containsMouse ? Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.06) : Theme.clear(Theme.text)
                Behavior on color { ColorAnimation { duration: Theme.fast } }
                Text {
                    id: label; anchors.centerIn: parent
                    width: Math.min(implicitWidth, opt.width - 12); elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                    text: opt.modelData.label; font.family: Theme.ui; font.pixelSize: Theme.px(13)
                    font.weight: opt.on ? Font.DemiBold : Font.Normal
                    color: opt.on ? Theme.text : Theme.muted
                    Behavior on color { ColorAnimation { duration: Theme.normal } }
                }
                MouseArea {
                    id: area; anchors.fill: parent; hoverEnabled: true; enabled: seg.enabled
                    cursorShape: Qt.PointingHandCursor; onClicked: seg.picked(opt.modelData.key)
                }
                ToolTip.visible: area.containsMouse && !!opt.modelData.hint; ToolTip.delay: 400
                ToolTip.text: opt.modelData.hint || ""
            }
        }
    }
}
