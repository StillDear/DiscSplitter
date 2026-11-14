import QtQuick
import QtQuick.Layouts
Rectangle {
    default property alias rows: col.data
    Layout.fillWidth: true
    implicitHeight: col.implicitHeight + 2
    radius: 10; color: Theme.raised; border.color: Theme.line2; clip: true
    ColumnLayout { id: col; x: 1; y: 1; width: parent.width - 2; spacing: 0 }
}
