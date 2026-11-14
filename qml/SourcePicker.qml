import QtQuick
import QtQuick.Controls
// Data-source selector for narrow panels. Styled like the text fields it sits with;
// the menu opens below at the same width.
AbstractButton {
    id: picker
    property string current: "musicbrainz"
    readonly property var sources: [
        { key: "itunes", label: "Apple Music" }, { key: "deezer", label: "Deezer" },
        { key: "musicbrainz", label: "MusicBrainz" }, { key: "discogs", label: "Discogs" }]
    signal picked(string key)
    readonly property string currentLabel: {
        for (let i = 0; i < sources.length; i++) if (sources[i].key === current) return sources[i].label
        return current
    }
    implicitHeight: Math.round(34 * Math.max(1, Theme.fontScale))
    implicitWidth: 160
    opacity: enabled ? 1 : 0.5
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: currentLabel
    contentItem: Item {}
    background: Rectangle {
        radius: 8; color: Theme.field
        border.color: menu.visible || picker.visualFocus ? Theme.accent : picker.hovered ? Theme.muted : Theme.line2
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        Text {
            anchors.left: parent.left; anchors.leftMargin: 10; anchors.right: chevron.left; anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: picker.currentLabel; color: Theme.text; elide: Text.ElideRight
            font.family: Theme.ui; font.pixelSize: Theme.px(13)
        }
        Icon {
            id: chevron
            kind: "down"; ink: Theme.muted; width: 14; height: 14
            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
            rotation: menu.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        }
    }
    onClicked: menu.visible ? menu.close() : menu.popup(picker, 0, picker.height + 4)
    AppMenu {
        id: menu
        minWidth: picker.width
        Repeater {
            model: picker.sources
            AppMenuItem {
                required property var modelData
                text: modelData.label
                checkable: true; checked: modelData.key === picker.current
                onTriggered: picker.picked(modelData.key)
            }
        }
    }
}
