import QtQuick
import QtQuick.Layouts
RowLayout {
    property alias text: title.text
    property alias note: noteText.text
    spacing: 8
    Copy { id: title; font.pixelSize: Theme.px(14); font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
    Copy { id: noteText; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap; visible: text !== "" }
}
