import QtQuick
Rectangle {
    property int padding: 16
    property bool flat: false   // a section inside a larger surface: no fill, frame or rounding of its own
    default property alias content: inner.data
    color: flat ? "transparent" : Theme.panel; border.color: flat ? "transparent" : Theme.line; radius: flat ? 0 : 14
    clip: true          // a panel squeezed by the layout never spills its content onto its neighbours
    Item { id: inner; anchors.fill: parent; anchors.margins: parent.padding }
}
