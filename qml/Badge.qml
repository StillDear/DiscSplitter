import QtQuick
// Small status label. tone: "good", "accent", "danger" or "neutral".
Rectangle {
    property alias text: label.text
    property string tone: "neutral"
    implicitWidth: label.implicitWidth + 16; implicitHeight: Math.round(22 * Math.max(1, Theme.fontScale)); radius: height / 2
    color: tone === "good" ? Theme.goodBg : tone === "accent" ? Theme.accentSoft2 : tone === "danger" ? Theme.dangerBg : Theme.chip
    Text {
        // Ends in "…" when the badge is given less room than its text
        id: label; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 16); elide: Text.ElideRight
        font.family: Theme.ui; font.pixelSize: Theme.px(11)
        color: parent.tone === "good" ? Theme.goodText : parent.tone === "accent" ? Theme.accentText : parent.tone === "danger" ? Theme.danger : Theme.sub
    }
}
