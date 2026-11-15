import QtQuick
Rectangle {
    property alias text: label.text
    property bool mono: false
    property int pad: 14                                // inner padding, both sides together
    readonly property real labelWidth: label.implicitWidth
    implicitWidth: label.implicitWidth + pad; implicitHeight: Math.round(20 * Math.max(1, Theme.fontScale))
    radius: 5; color: Theme.chip
    Text { id: label; anchors.centerIn: parent; color: Theme.sub; font.family: parent.mono ? Theme.mono : Theme.ui; font.pixelSize: Theme.px(11)}
}
