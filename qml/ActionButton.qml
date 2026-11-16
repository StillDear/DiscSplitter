import QtQuick
import QtQuick.Controls
Button {
    id: control
    property bool primary: false
    property bool selected: false
    property bool danger: false
    property bool ghost: false
    property bool large: false
    property string iconKind: ""        // an icon before the text (Icon kinds)
    property bool iconSpinning: false
    // A disc's sheen on the edge (the M2TS copy of a disc); sweep() runs a band of light across it once.
    property bool sheen: false
    function sweep() { buttonSheen.sweep() }
    // A primary button that cannot be pressed looks like any other disabled button: a faded
    // orange reads as "working on it" rather than "not yet".
    readonly property bool accent: primary && enabled
    implicitHeight: Math.round((large ? 40 : 32) * Math.max(1, Theme.fontScale))
    implicitWidth: Math.max(large ? 120 : 64, contentItem.implicitWidth + (large ? 44 : 26))
    font.pixelSize: Theme.px(large ? 14 : 13); font.family: Theme.ui; font.bold: accent
    padding: 0
    opacity: enabled ? 1 : 0.45
    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    readonly property color ink: control.accent ? Theme.accentInk : control.danger ? Theme.danger : control.selected ? Theme.accentText : Theme.text
    contentItem: Item {
        implicitWidth: label.implicitWidth + (glyph.visible ? glyph.width + 8 : 0)
        implicitHeight: label.implicitHeight
        Row {
            anchors.centerIn: parent; spacing: 8
            width: Math.min(implicitWidth, parent.width)
            Icon {
                id: glyph
                visible: control.iconKind !== ""; kind: control.iconKind || "disc"; ink: control.ink
                width: Math.round(control.font.pixelSize * 1.25); height: width; anchors.verticalCenter: parent.verticalCenter
                RotationAnimation on rotation {
                    running: Theme.animate && control.iconSpinning && glyph.visible
                    from: 0; to: 360; duration: 1600; loops: Animation.Infinite
                    onRunningChanged: if (!running) glyph.rotation = 0
                }
            }
            Text {
                id: label
                width: Math.min(implicitWidth, control.availableWidth - (glyph.visible ? glyph.width + 8 : 0))
                text: control.text; font: control.font; color: control.ink
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }
    background: Rectangle {
        radius: control.large ? 10 : 8
        color: control.accent ? (control.down ? Qt.darker(Theme.accent, 1.12) : control.hovered ? Qt.lighter(Theme.accent, 1.08) : Theme.accent)
             : control.selected ? Theme.accentSoft
             : control.ghost ? (control.hovered ? Theme.raised : Theme.clear(Theme.raised))
             : control.danger ? Theme.clear(Theme.raised)
             : (control.down ? Theme.segOn : control.hovered ? Qt.lighter(Theme.raised, Theme.light ? 0.97 : 1.18) : Theme.raised)
        border.color: control.visualFocus ? Theme.accent
             : control.accent || control.ghost ? Theme.clear(Theme.line2)
             : control.selected ? Theme.accent
             : control.danger ? Theme.dangerLine : Theme.line2
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        Sheen { id: buttonSheen; anchors.fill: parent; radius: parent.radius; on: control.sheen; lineWidth: 2 }
    }
}
