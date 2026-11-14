import QtQuick
// Drag handle that lives in the gap between two panels (give it negative margins equal to the
// layout spacing). It reports the size the panel would get; the page applies it live and saves it
// on release. Double-click returns the panel to its default size.
Item {
    id: handle
    property bool vertical: true          // a vertical bar: drag left / right to change a width
    property real size: 0                 // the panel's current size
    property int direction: 1             // +1: dragging right / down grows the panel, -1: shrinks it
    property real minimum: 0
    property real maximum: 100000
    property bool divider: false          // draw a hairline between the two sections it separates
    readonly property bool dragging: mouse.pressed && mouse.moved
    signal resized(real value)            // live, while dragging
    signal committed(real value)          // drag finished
    signal reset()
    implicitWidth: vertical ? 12 : 0
    implicitHeight: vertical ? 0 : 12
    function clamp(value) { return Math.max(minimum, Math.min(maximum, value)) }

    Rectangle {
        visible: handle.divider
        anchors.centerIn: parent
        width: handle.vertical ? 1 : parent.width; height: handle.vertical ? parent.height : 1
        color: Theme.line
    }
    Rectangle {
        anchors.centerIn: parent
        width: handle.vertical ? 3 : Math.min(56, parent.width)
        height: handle.vertical ? Math.min(56, parent.height) : 3
        radius: 1.5; color: handle.dragging ? Theme.accent : Theme.muted
        opacity: handle.dragging ? 0.9 : mouse.containsMouse ? 0.55 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent; hoverEnabled: true
        cursorShape: handle.vertical ? Qt.SplitHCursor : Qt.SplitVCursor
        property real origin: 0
        property real start: 0
        property real last: 0
        property bool moved: false
        onPressed: function(event) {
            const point = mapToItem(null, event.x, event.y)
            origin = handle.vertical ? point.x : point.y
            start = last = handle.size
            moved = false
        }
        onPositionChanged: function(event) {
            if (!pressed) return
            const point = mapToItem(null, event.x, event.y)
            const delta = (handle.vertical ? point.x : point.y) - origin
            if (!moved && Math.abs(delta) < 2) return
            moved = true
            last = handle.clamp(start + handle.direction * delta)
            handle.resized(last)
        }
        onReleased: if (moved) { moved = false; handle.committed(last) }
        onDoubleClicked: handle.reset()
    }
}
