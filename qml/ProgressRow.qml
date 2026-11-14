import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Rectangle {
    id: progressRow
    required property int number
    required property string title
    required property string file
    required property string duration
    required property string status
    required property string verify        // "" (not checked) | "ok" | "warn"
    required property string verifyText
    property bool showMark: false
    property var texts: backend.texts
    readonly property bool flagged: status === "done" && verify === "warn"
    readonly property color tone: flagged ? Theme.danger : status === "done" ? Theme.goodText : status === "failed" ? Theme.danger : status === "running" ? Theme.accentText : Theme.faint
    height: Theme.rowHeight; radius: 8
    color: status === "running" || status === "failed" || flagged ? Theme.raised : "transparent"
    Behavior on color { ColorAnimation { duration: Theme.normal } }
    HoverHandler { id: rowHover }
    ToolTip.visible: progressRow.flagged && rowHover.hovered
    ToolTip.delay: 200
    ToolTip.text: progressRow.verifyText
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 12
        Rectangle {
            readonly property bool good: progressRow.status === "done" && !progressRow.flagged
            visible: progressRow.showMark
            Layout.preferredWidth: 18; Layout.preferredHeight: 18; radius: 9
            color: good ? Theme.good : "transparent"
            border.color: good ? Theme.good : progressRow.tone
            Icon { anchors.fill: parent; anchors.margins: 3; kind: parent.good ? "check" : "alert"; ink: parent.good ? Theme.panel : progressRow.tone; visible: progressRow.status === "done" || progressRow.status === "failed" }
        }
        Copy { visible: !progressRow.showMark; text: progressRow.number.toString().padStart(2, "0"); font.family: Theme.mono; color: Theme.muted; Layout.preferredWidth: 24; wrapMode: Text.NoWrap }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 0
            Copy {
                text: progressRow.file || progressRow.title; Layout.fillWidth: true; elide: Text.ElideRight; maximumLineCount: 1; wrapMode: Text.NoWrap
                font.pixelSize: Theme.px(14); font.weight: Font.Medium
                color: progressRow.status === "pending" ? Theme.muted : Theme.text
            }
            Copy {
                visible: progressRow.flagged
                text: progressRow.verifyText.split("\n")[0]; Layout.fillWidth: true; elide: Text.ElideRight; maximumLineCount: 1; wrapMode: Text.NoWrap
                font.pixelSize: Theme.px(11); color: Theme.danger
            }
        }
        Copy { text: progressRow.duration; font.family: Theme.mono; font.pixelSize: Theme.px(12); color: Theme.muted; Layout.preferredWidth: 52; horizontalAlignment: Text.AlignRight; wrapMode: Text.NoWrap }
        Copy {
            text: progressRow.flagged ? progressRow.texts.verifyCheckFailed : progressRow.texts[progressRow.status] || progressRow.status
            color: progressRow.tone; Layout.preferredWidth: 90; horizontalAlignment: Text.AlignRight; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
        }
    }
}
