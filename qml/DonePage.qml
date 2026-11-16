import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
RowLayout {
    id: donePage
    required property var win
    readonly property bool clean: win.exportView.result === "done" && win.exportView.failed === 0 && win.exportView.remaining === 0
    readonly property int unfinished: win.exportView.failed + win.exportView.remaining
    readonly property bool flagged: win.exportView.verifyState === "done" && win.exportView.verifyIssues > 0
    // good: all done and checked · warn: all done, some failed the check · bad: files unfinished
    readonly property string outcome: unfinished > 0 || (win.exportView.result !== "done" && win.exportView.completed === 0) ? "bad"
                                      : flagged ? "warn" : "good"
    spacing: 12
    onVisibleChanged: if (visible) resultPop.restart()
    SequentialAnimation {
        id: resultPop
        PropertyAction { target: resultBadge; property: "scale"; value: Theme.animate ? 0.4 : 1 }
        PropertyAction { target: resultBadge; property: "opacity"; value: Theme.animate ? 0 : 1 }
        PauseAnimation { duration: Theme.fast }
        ParallelAnimation {
            NumberAnimation { target: resultBadge; property: "scale"; to: 1; duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 2 }
            NumberAnimation { target: resultBadge; property: "opacity"; to: 1; duration: Theme.normal }
        }
    }

    Card {
        Layout.preferredWidth: 400; Layout.fillHeight: true; padding: 24
        ColumnLayout {
            anchors.fill: parent; spacing: 18
          // What happened scrolls on a short window; the buttons below always stay in view.
          Flickable {
            id: doneScroll
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: doneInfo.implicitHeight; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: SlimScrollBar {}
          ColumnLayout {
            id: doneInfo
            width: doneScroll.width; spacing: 18
            Rectangle {
                id: resultBadge
                Layout.preferredWidth: 40; Layout.preferredHeight: 40; radius: 20
                color: donePage.outcome === "good" ? Theme.goodBg : donePage.outcome === "warn" ? Theme.accentSoft2 : Theme.dangerBg
                Icon {
                    anchors.centerIn: parent; width: 20; height: 20
                    kind: donePage.outcome === "good" ? "check" : "alert"
                    ink: donePage.outcome === "good" ? Theme.good : donePage.outcome === "warn" ? Theme.accentText : Theme.danger
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 8
                Copy {
                    text: donePage.unfinished > 0 ? win.fmt("doneTitlePartial", { n: win.exportView.completed, f: donePage.unfinished }) : win.fmt("doneTitle", { n: win.exportView.completed })
                    font.pixelSize: Theme.display; font.weight: Theme.strong; Layout.fillWidth: true; lineHeight: 1.15
                }
                Copy { text: [win.discView.artist, win.discView.album].filter(function(x) { return x }).join(" – ") || win.tr(win.exportView.result); color: Theme.muted; Layout.fillWidth: true }
            }
            Rectangle {
                visible: donePage.unfinished > 0
                Layout.fillWidth: true; Layout.preferredHeight: warnCol.implicitHeight + 28; radius: 10
                color: Theme.dangerBg; border.color: Theme.dangerLine
                ColumnLayout {
                    id: warnCol; x: 14; y: 14; width: parent.width - 28; spacing: 10
                    Copy { text: win.fmt("unfinishedTitle", { n: donePage.unfinished }); font.weight: Font.DemiBold; color: Theme.danger; Layout.fillWidth: true }
                    Copy { text: win.tr("checkpointHint"); font.pixelSize: Theme.px(12); color: Theme.sub; Layout.fillWidth: true; lineHeight: 1.3 }
                    RowLayout {
                        spacing: 8
                        ActionButton { text: win.tr("retry"); primary: true; visible: win.exportView.resume; enabled: !win.appView.working; onClicked: backend.exporter.resume() }
                        ActionButton { text: win.tr("openLog"); onClicked: backend.exporter.openLog() }
                    }
                }
            }
            // Every finished file was read back: its length, streams and title tag.
            Rectangle {
                visible: win.exportView.verifyState === "done" && win.exportView.verifyIssues > 0
                Layout.fillWidth: true; Layout.preferredHeight: verifyCol.implicitHeight + 28; radius: 10
                color: Theme.dangerBg; border.color: Theme.dangerLine
                ColumnLayout {
                    id: verifyCol; x: 14; y: 14; width: parent.width - 28; spacing: 10
                    Copy { text: win.fmt("verifySomeIssues", { f: win.exportView.verifyIssues }); font.weight: Font.DemiBold; color: Theme.danger; Layout.fillWidth: true }
                    Copy { text: win.tr("verifyIssuesHint"); font.pixelSize: Theme.px(12); color: Theme.sub; Layout.fillWidth: true; lineHeight: 1.3 }
                    RowLayout {
                        spacing: 8
                        ActionButton { text: win.tr("reexportFlagged"); primary: true; enabled: !win.appView.working && !win.exportView.resume; onClicked: backend.exporter.reexportFlagged() }
                        ActionButton { text: win.tr("openLog"); onClicked: backend.exporter.openLog() }
                    }
                }
            }
            RowLayout {
                visible: win.exportView.verifyState === "done" && win.exportView.verifyIssues === 0 && win.exportView.verified > 0
                Layout.fillWidth: true; spacing: 8
                Icon { kind: "check"; ink: Theme.good; Layout.preferredWidth: 14; Layout.preferredHeight: 14 }
                Copy { text: win.fmt("verifyAllOk", { n: win.exportView.verified }); color: Theme.goodText; font.pixelSize: Theme.px(12); Layout.fillWidth: true }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 5
                Copy { text: win.tr("location"); font.pixelSize: Theme.px(12); color: Theme.faint }
                Copy { text: win.nativePath(win.exportView.destination); font.family: Theme.mono; font.pixelSize: Theme.px(12); Layout.fillWidth: true; wrapMode: Text.Wrap; lineHeight: 1.2 }
            }
          }
          }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 8
                ActionButton { text: win.tr("openOutput"); large: true; font.bold: true; Layout.fillWidth: true; onClicked: backend.exporter.openOutput() }
                ActionButton { text: win.tr("rerun"); large: true; Layout.fillWidth: true; enabled: !win.appView.working; onClicked: backend.navigate("main") }
                ActionButton { text: win.tr("nextDisc"); large: true; Layout.fillWidth: true; enabled: !win.appView.working; onClicked: backend.navigate("start") }
            }
        }
    }

    Card {
        Layout.fillWidth: true; Layout.fillHeight: true; padding: 20
        ColumnLayout {
            anchors.fill: parent; spacing: 10
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                Copy { text: win.tr("outputFile"); font.pixelSize: Theme.title; font.weight: Theme.strong; Layout.fillWidth: true; wrapMode: Text.NoWrap }
                Badge { tone: "good"; text: win.tr("done") + " " + win.exportView.completed }
                Badge { visible: donePage.unfinished > 0; tone: "danger"; text: win.tr("unfinishedShort") + " " + donePage.unfinished }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12 + doneBar.gutter; spacing: 12
                Item { Layout.preferredWidth: 18 }
                Copy { text: win.tr("outputFile"); Layout.fillWidth: true; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                Copy { text: win.tr("duration"); Layout.preferredWidth: 52; horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
                Copy { text: win.tr("status"); Layout.preferredWidth: 90; horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap }
            }
            ListView {
                Layout.fillWidth: true; Layout.fillHeight: true; model: exportModel; clip: true; spacing: 2
                ScrollBar.vertical: SlimScrollBar { id: doneBar }
                populate: ListEnter {}
                add: ListEnter {}
                delegate: ProgressRow { width: ListView.view.width - doneBar.gutter; showMark: true }
            }
        }
    }
}
