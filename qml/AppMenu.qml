import QtQuick
import QtQuick.Controls
// App-themed popup menu: rounded panel like the cards, soft hover, fade/scale in.
Menu {
    id: menu
    property int minWidth: 200
    padding: 6
    implicitWidth: Math.max(minWidth, contentItem.implicitWidth + leftPadding + rightPadding)
    delegate: AppMenuItem {}
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: Theme.animate ? 0.97 : 1; to: 1; duration: Theme.fast; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }
    background: Rectangle {
        implicitWidth: menu.minWidth
        color: Theme.panel; radius: 10; border.color: Theme.line2
        // soft drop shadow made of two offset layers (no extra effects module needed)
        Rectangle { z: -1; anchors.fill: parent; anchors.topMargin: 3; anchors.leftMargin: -1; anchors.rightMargin: -1; anchors.bottomMargin: -5; radius: 12; color: Qt.rgba(0, 0, 0, Theme.light ? 0.06 : 0.25) }
        Rectangle { z: -2; anchors.fill: parent; anchors.topMargin: 6; anchors.leftMargin: -3; anchors.rightMargin: -3; anchors.bottomMargin: -10; radius: 14; color: Qt.rgba(0, 0, 0, Theme.light ? 0.04 : 0.18) }
    }
}
