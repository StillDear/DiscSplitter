import QtQuick
import QtQuick.Controls
// "Check connection", beside an online search: reaches the chosen catalogue once and says whether it
// answered and how fast. The answer stays in place of the link (a dot and a word) until the source
// changes; clicking it checks again, and its tooltip carries the error in full.
AbstractButton {
    id: control
    property string source: ""
    readonly property var result: win.appView.sourceCheck || ({})
    readonly property string state_: result.source === source ? (result.state || "") : ""
    readonly property bool running: state_ === "running"
    readonly property color tone: state_ === "ok" ? Theme.good : state_ === "running" ? Theme.faint : Theme.danger
    readonly property string label: state_ === "ok" ? win.tr("sourceOk") + " · " + result.ms + " ms"
                                  : state_ === "blocked" ? win.tr("netBlocked")
                                  : state_ === "error" ? win.tr("netError")
                                  : state_ === "running" ? win.tr("netRunning") : win.tr("sourceCheck")
    implicitHeight: 24; implicitWidth: row.implicitWidth
    hoverEnabled: true
    enabled: !win.appView.working || running
    Accessible.name: label
    onClicked: if (!running) backend.checkSource(source)
    HoverHandler { cursorShape: control.running ? Qt.ArrowCursor : Qt.PointingHandCursor }
    ToolTip.visible: hovered && !running; ToolTip.delay: 500
    ToolTip.text: state_ === "" ? win.tr("sourceCheckTip")
                : (result.detail ? result.detail + "\n\n" : "") + win.tr("sourceRetry")
    contentItem: Item {
        Row {
            id: row
            spacing: 6; anchors.verticalCenter: parent.verticalCenter
            // Before the first check: the refresh mark; afterwards a dot in the answer's colour
            Icon {
                visible: control.state_ === ""
                kind: "refresh"; width: 12; height: 12; anchors.verticalCenter: parent.verticalCenter
                ink: control.hovered ? Theme.text : Theme.muted
            }
            Rectangle {
                visible: control.state_ !== ""
                width: 7; height: 7; radius: 3.5; color: control.tone; anchors.verticalCenter: parent.verticalCenter
                SequentialAnimation on opacity {
                    running: control.running && Theme.animate; loops: Animation.Infinite
                    onRunningChanged: if (!running) parent.opacity = 1
                    NumberAnimation { to: 0.25; duration: 500; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1; duration: 500; easing.type: Easing.InOutSine }
                }
            }
            Copy {
                text: control.label; font.pixelSize: Theme.small; wrapMode: Text.NoWrap
                font.family: Theme.num; font.features: Theme.tabular
                anchors.verticalCenter: parent.verticalCenter
                color: control.state_ === "ok" ? Theme.goodText
                     : control.state_ === "error" || control.state_ === "blocked" ? Theme.danger
                     : control.hovered ? Theme.text : Theme.muted
            }
        }
    }
    background: Item {}
}
