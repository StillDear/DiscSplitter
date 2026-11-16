import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
ColumnLayout {
    id: exportPage
    required property var win
    readonly property var stages: ["extracting", "splitting", "cleanup", "verifying"]
    readonly property int stageIndex: stages.indexOf(win.exportView.stage)
    spacing: 12
    property real shownCompleted: win.exportView.completed
    Behavior on shownCompleted { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }

    Card {
        Layout.fillWidth: true; Layout.preferredHeight: 206; padding: 24
        ColumnLayout {
            anchors.fill: parent; spacing: 16
            RowLayout {
                Layout.fillWidth: true; spacing: 20
                // Cutting a copy of the disc: the disc, in its own colours, turns while the engine reads it.
                Icon {
                    id: spinningDisc
                    visible: win.discView.outputFormat === "m2ts"; kind: "disc"; sheen: true
                    Layout.preferredWidth: 44; Layout.preferredHeight: 44; Layout.alignment: Qt.AlignVCenter
                    RotationAnimation on rotation {
                        running: Theme.animate && spinningDisc.visible && win.appView.pipeline
                                 && win.exportView.result !== "cancelling"
                        from: 0; to: 360; duration: 2400; loops: Animation.Infinite
                        onRunningChanged: if (!running) spinningDisc.rotation = 0
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    Copy { text: (win.discView.album ? win.discView.album + " · " : "") + win.fmt("stageOf", { i: Math.max(1, exportPage.stageIndex + 1) }); color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                    Copy {
                        text: win.tr(win.exportView.stage) + (win.exportView.current ? " · " + win.fmt("chapterN", { n: win.exportView.current }) : "")
                        font.pixelSize: Theme.display; font.weight: Theme.strong; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                    }
                }
                Copy { text: Math.round(exportPage.shownCompleted) + " / " + progressList.count; color: Theme.text; font.pixelSize: Theme.display; font.weight: Theme.strong; font.features: Theme.tabular; wrapMode: Text.NoWrap }
                ActionButton {
                    large: true; text: win.tr(win.exportView.result === "cancelling" ? "cancelling" : "cancelJob")
                    enabled: win.exportView.result !== "cancelling"; onClicked: backend.exporter.cancel()
                }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 3; Layout.preferredHeight: 10; Layout.maximumHeight: 10
                Repeater {
                    model: exportModel
                    Rectangle {
                        required property real seconds
                        required property string status
                        required property int number
                        // How far into this chapter the cut is, when the tool says (M2TS and MKV do; FLAC does not)
                        readonly property real fraction: status === "running" && number === win.exportView.current ? win.exportView.chapterFraction : 0
                        Layout.fillWidth: true; Layout.preferredWidth: Math.max(1, seconds); Layout.fillHeight: true; radius: 5
                        id: seg
                        color: status === "done" ? Theme.good : status === "running" ? (fraction > 0 ? Theme.accentSoft : Theme.accent) : status === "failed" ? Theme.danger : Theme.chip
                        Behavior on color { ColorAnimation { duration: Theme.slow } }
                        Rectangle {
                            visible: seg.fraction > 0; radius: 5; color: Theme.accent
                            anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                            width: Math.max(height, parent.width * seg.fraction)
                            Behavior on width { NumberAnimation { duration: Theme.normal } }
                        }
                        // The chapter being split breathes gently.
                        SequentialAnimation on opacity {
                            running: Theme.animate && seg.status === "running"; loops: Animation.Infinite
                            NumberAnimation { to: 0.45; duration: 700; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1; duration: 700; easing.type: Easing.InOutSine }
                            onRunningChanged: if (!running) seg.opacity = 1
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 10
                Repeater {
                    model: exportPage.stages
                    Rectangle {
                        id: stageCard
                        required property int index
                        required property string modelData
                        readonly property int phase: index < exportPage.stageIndex ? 0 : index === exportPage.stageIndex ? 1 : 2
                        Layout.fillWidth: true; Layout.preferredHeight: 58; radius: 10
                        color: phase === 0 ? Theme.goodBg : phase === 1 ? Theme.accentSoft : Theme.raised
                        border.color: phase === 1 ? Theme.accent : "transparent"
                        Behavior on color { ColorAnimation { duration: Theme.slow } }
                        Behavior on border.color { ColorAnimation { duration: Theme.slow } }
                        ColumnLayout {
                            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; anchors.topMargin: 9; anchors.bottomMargin: 9; spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                Copy { text: (stageCard.index + 1) + "  " + win.tr(stageCard.modelData); font.weight: Font.DemiBold; color: stageCard.phase === 2 ? Theme.muted : Theme.text; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                                BusyIndicator { running: win.appView.pipeline && stageCard.phase === 1; visible: running; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                                Copy {
                                    text: win.tr(stageCard.phase === 0 ? "done" : stageCard.phase === 1 ? "running" : "waiting"); font.pixelSize: Theme.px(12); wrapMode: Text.NoWrap
                                    color: stageCard.phase === 0 ? Theme.goodText : stageCard.phase === 1 ? Theme.accentText : Theme.faint
                                }
                            }
                            Copy {
                                text: win.tr((win.discView.outputFormat === "flac" ? ["stageExtractDetail", "stageSplitFlac", "stageCleanDetail", "stageVerifyDetail"]
                                              : win.discView.outputFormat === "m2ts" ? ["stageExtractEngine", "stageSplitM2ts", "stageCleanM2ts", "stageVerifyDetail"]
                                              : ["stageExtractDirect", "stageSplitDirect", "stageCleanDirect", "stageVerifyDetail"])[stageCard.index])
                                font.pixelSize: Theme.px(12); color: stageCard.phase === 2 ? Theme.faint : Theme.sub; Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }
    }

    // The songs take the page; the log stays one quiet line until asked for.
    Card {
        Layout.fillWidth: true; Layout.fillHeight: true; padding: 16
        ColumnLayout {
            anchors.fill: parent; spacing: 6
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12 + progressBar.gutter; spacing: 12
                Copy { text: "#"; Layout.preferredWidth: 24; color: Theme.faint; font.pixelSize: Theme.small }
                Copy { text: win.tr("outputFile"); Layout.fillWidth: true; color: Theme.faint; font.pixelSize: Theme.small; wrapMode: Text.NoWrap }
                Copy { text: win.tr("duration"); Layout.preferredWidth: 52; horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.small; wrapMode: Text.NoWrap }
                Copy { text: win.tr("status"); Layout.preferredWidth: 90; horizontalAlignment: Text.AlignRight; color: Theme.faint; font.pixelSize: Theme.small; wrapMode: Text.NoWrap }
            }
            ListView {
                id: progressList; Layout.fillWidth: true; Layout.fillHeight: true; model: exportModel; clip: true; spacing: 2
                ScrollBar.vertical: SlimScrollBar { id: progressBar }
                populate: ListEnter {}
                add: ListEnter {}
                delegate: ProgressRow { width: ListView.view.width - progressBar.gutter }
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
            ScrollView {
                id: logScroll
                visible: logToggle.open
                Layout.fillWidth: true; Layout.preferredHeight: 180; clip: true
                rightPadding: logBar.gutter
                ScrollBar.vertical: SlimScrollBar { id: logBar; parent: logScroll; x: logScroll.mirrored ? 0 : logScroll.width - width; y: logScroll.topPadding; height: logScroll.availableHeight }
                TextArea {
                    id: logText; ContextMenu.menu: EditMenu { target: logText }
                    text: win.exportView.logs; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.muted
                    font.family: Theme.mono; font.pixelSize: Theme.caption; padding: 12
                    background: Rectangle { color: Theme.deep; radius: 10; border.color: Theme.line }
                }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 4; spacing: 12
                Disclosure { id: logToggle; text: win.tr("log") }
                Copy {
                    // The newest log line, so progress is legible without the full log
                    readonly property string all: win.exportView.logs.replace(/\s+$/, "")
                    text: logToggle.open ? "" : all.slice(all.lastIndexOf("\n") + 1)
                    color: Theme.faint; font.family: Theme.mono; font.pixelSize: Theme.caption
                    Layout.fillWidth: true; wrapMode: Text.NoWrap; elide: Text.ElideRight
                }
                ActionButton { visible: logToggle.open; text: win.tr("openLog"); implicitHeight: 28; onClicked: backend.exporter.openLog() }
                Copy {
                    text: win.nativePath(win.exportView.destination); color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.caption
                    Layout.maximumWidth: 320; elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                }
                ActionButton { text: win.tr("openOutput"); implicitHeight: 28; onClicked: backend.exporter.openOutput() }
            }
        }
    }
}
