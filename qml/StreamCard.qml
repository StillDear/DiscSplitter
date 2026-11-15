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
                // The tag sits beside the title when both fit whole; otherwise it moves to the start of the
                // line of extra facts, so neither is ever cut short.
                readonly property bool tagInline: card.tag === ""
                    || width >= titleText.implicitWidth + tagText.implicitWidth + 24 + 2 * spacing
                Copy {
                    id: titleText
                    text: card.title; font.pixelSize: Theme.item; font.weight: Font.DemiBold
                    Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                }
                Copy {
                    id: tagText
                    visible: card.tag !== "" && titleRow.tagInline; text: card.tag; font.pixelSize: Theme.small; color: Theme.accentText
                    wrapMode: Text.NoWrap
                }
                IconButton {
                    iconKind: "info"; implicitWidth: 24; implicitHeight: 22
                    onClicked: card.details()
                    ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: card.detailsTip
                    Accessible.name: card.detailsTip + " " + card.accessibleName
                }
            }
            // One row of chips: when the row runs short they tighten (less padding and spacing) before
            // any chip has to wrap onto a second line.
            Flow {
                id: chipRow
                Layout.fillWidth: true; visible: card.chips.length > 0
                readonly property real labels: {
                    let sum = 0
                    for (let i = 0; i < chipRepeater.count; i++) { const c = chipRepeater.itemAt(i); if (c) sum += c.labelWidth }
                    return sum
                }
                readonly property bool tight: width < labels + chipRepeater.count * 14 + (chipRepeater.count - 1) * 6
                spacing: tight ? 4 : 6
                Repeater { id: chipRepeater; model: card.chips; Chip { required property string modelData; text: modelData; pad: chipRow.tight ? 8 : 14 } }
            }
            // Extra facts, led by the tag when it moved down; a second line rather than a cut-off fact.
            Copy {
                function escaped(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
                visible: card.extra !== "" || !titleRow.tagInline
                textFormat: titleRow.tagInline ? Text.PlainText : Text.StyledText
                text: titleRow.tagInline ? card.extra
                    : "<font color='" + Theme.accentText + "'>" + escaped(card.tag) + "</font>"
                      + (card.extra !== "" ? " · " + escaped(card.extra) : "")
                color: Theme.muted; font.pixelSize: Theme.small
                Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
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
