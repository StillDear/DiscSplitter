import QtQuick
import QtQuick.Controls

// The app's vertical scroll bar: a slim themed handle, faint at rest and solid while hovered,
// dragged or scrolling. Content beside it should leave `gutter` free (rows: width minus gutter),
// so the bar sits in its own lane instead of on top of text and buttons.
ScrollBar {
    id: bar
    readonly property bool needed: size < 1 && policy !== ScrollBar.AlwaysOff
    readonly property real gutter: needed ? width + 4 : 0
    policy: ScrollBar.AsNeeded
    padding: 2
    minimumSize: 0.08
    implicitWidth: 10
    background: null
    contentItem: Rectangle {
        implicitWidth: 6
        radius: width / 2
        color: bar.pressed ? Theme.muted : bar.hovered ? Theme.faint : Theme.line2
        opacity: !bar.needed ? 0 : bar.active || bar.hovered || bar.pressed ? 1 : 0.6
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
}
