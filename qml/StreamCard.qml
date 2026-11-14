import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One stream (the video, an audio track, a subtitle track) in the workspace's right column.
// Every kind has the same layout: a lead column (checkbox, or an icon when it cannot be chosen),
// a title line with an optional tag and the details button in the corner, one row of chips,
// and a muted line of extra facts.
Rectangle {
    id: card
    property string title: ""
    property string tag: ""
    property var chips: []
    property string extra: ""
    property bool selectable: true
    property bool checked: false
    property bool interactive: true
    property string leadIcon: ""
    property string detailsTip: ""
    property string accessibleName: title
    signal toggled()
    signal details()

    implicitHeight: body.implicitHeight + 24
    radius: 10; color: Theme.raised
    border.color: card.selectable && card.checked ? Theme.accent : hit.hovered && card.interactive ? Theme.faint : Theme.line2
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }

    RowLayout {
        id: body
        x: 12; y: 12; width: parent.width - 24; spacing: 10
        // Lead column: the same width for every kind, centred on the title line
        Item {
            Layout.preferredWidth: 18; Layout.preferredHeight: titleRow.implicitHeight; Layout.alignment: Qt.AlignTop
            SelectionMark { visible: card.selectable; checked: card.checked; anchors.verticalCenter: parent.verticalCenter }
            Icon {
                visible: !card.selectable && card.leadIcon !== ""; kind: card.leadIcon; ink: Theme.muted
                width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 6
            RowLayout {
                id: titleRow
                Layout.fillWidth: true; spacing: 8
                // The title keeps its full width; when space runs out the tag gives way first.
                Copy {
                    text: card.title; font.pixelSize: Theme.px(14); font.weight: Font.DemiBold
                    Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                    Layout.minimumWidth: Math.min(implicitWidth, Math.max(0, titleRow.width - 24 - 16))
                }
                Copy {
                    visible: card.tag !== ""; text: card.tag; font.pixelSize: Theme.px(12); color: Theme.accentText
                    wrapMode: Text.NoWrap; elide: Text.ElideRight; horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true; Layout.maximumWidth: implicitWidth; Layout.minimumWidth: 0
                }
                IconButton {
                    iconKind: "info"; implicitWidth: 24; implicitHeight: 22
                    onClicked: card.details()
                    ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: card.detailsTip
                    Accessible.name: card.detailsTip + " " + card.accessibleName
                }
            }
            Flow {
                Layout.fillWidth: true; spacing: 6; visible: card.chips.length > 0
                Repeater { model: card.chips; Chip { required property string modelData; text: modelData } }
            }
            Copy {
                visible: card.extra !== ""; text: card.extra; color: Theme.muted; font.pixelSize: Theme.px(12)
                Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
            }
        }
    }
    // The whole card toggles; it sits below the content so the details button keeps its own clicks.
    AbstractButton {
        id: hit
        anchors.fill: parent; z: -1; enabled: card.interactive; hoverEnabled: true
        Accessible.name: card.accessibleName
        onClicked: card.toggled()
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }
}
