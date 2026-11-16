import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
// The built-in help: guide, tips, FAQ, troubleshooting and about, laid out like the settings page
// (sections listed on the left, one scrolling column on the right). The text is gui/help_content.py.
Item {
    id: page
    required property var win
    readonly property var help: backend.helpContent
    readonly property var groups: [
        { key: "guide", label: win.tr("helpGuide"), block: guideBlock },
        { key: "tips", label: win.tr("tips"), block: tipsBlock },
        { key: "faq", label: win.tr("helpFaq"), block: faqBlock },
        { key: "troubleshoot", label: win.tr("helpTroubleshoot"), block: troubleshootBlock },
        { key: "about", label: win.tr("about"), block: aboutBlock }]
    readonly property int currentGroup: {
        const y = flick.contentY
        if (y >= flick.contentHeight - flick.height - 2 && y > 0) return groups.length - 1
        let found = 0
        for (let i = 0; i < groups.length; i++) if (groups[i].block.y - 24 <= y) found = i
        return found
    }
    function blockOf(key) {
        for (let i = 0; i < groups.length; i++) if (groups[i].key === key) return groups[i].block
        return guideBlock
    }
    // Opened from the menu (or F1) on a section: go there; animated only when the page is already showing.
    function showSection(animated) {
        const target = flick.topOf(blockOf(win.appView.helpSection))
        scrollTo.stop()
        if (animated) { scrollTo.to = target; scrollTo.start() } else flick.contentY = target
    }
    onVisibleChanged: if (visible) Qt.callLater(showSection, false)
    readonly property string section: win.appView.helpSection || "guide"
    onSectionChanged: if (visible) showSection(true)

    // A numbered step: circle with the number, title and a sentence or two.
    component StepRow: Rectangle {
        id: step
        required property int index
        required property var modelData
        Layout.fillWidth: true
        implicitHeight: stepText.implicitHeight + 26
        color: "transparent"
        Rectangle { visible: step.index > 0; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 1; color: Theme.line2 }
        Rectangle {
            id: badge
            x: 14; y: 14; width: 24; height: 24; radius: 12; color: Theme.accentSoft
            Copy { anchors.centerIn: parent; text: String(step.index + 1); color: Theme.accentText; font.pixelSize: Theme.small; font.weight: Theme.strong; wrapMode: Text.NoWrap }
        }
        ColumnLayout {
            id: stepText
            x: badge.x + badge.width + 12; y: 15; width: parent.width - x - 16; spacing: 4
            Copy { text: step.modelData.title; font.pixelSize: Theme.item; font.weight: Theme.strong; Layout.fillWidth: true }
            Copy { text: step.modelData.body; color: Theme.muted; lineHeight: 1.3; Layout.fillWidth: true }
        }
    }

    // A question that opens to its answer.
    component FaqRow: Item {
        id: faq
        required property int index
        required property var modelData
        property bool open: false
        Layout.fillWidth: true
        implicitHeight: header.height + (open ? answer.implicitHeight + 14 : 0)
        clip: true
        Behavior on implicitHeight { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        Rectangle { visible: faq.index > 0; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 1; color: Theme.line2 }
        AbstractButton {
            id: header
            width: parent.width; height: Math.max(48, question.implicitHeight + 24); hoverEnabled: true
            Accessible.name: faq.modelData.title
            Accessible.role: Accessible.Button
            onClicked: faq.open = !faq.open
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            background: Rectangle {
                color: header.hovered ? Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, Theme.light ? 0.04 : 0.05) : Theme.clear(Theme.text)
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
            contentItem: Item {
                Copy {
                    id: question
                    x: 14; width: parent.width - x - 44; anchors.verticalCenter: parent.verticalCenter
                    text: faq.modelData.title; font.weight: faq.open ? Font.DemiBold : Font.Normal
                }
                Icon {
                    kind: "down"; width: 14; height: 14; ink: header.hovered ? Theme.text : Theme.muted
                    anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter
                    rotation: faq.open ? 180 : 0
                    Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                }
            }
        }
        Copy {
            id: answer
            x: 14; y: header.height; width: parent.width - 28
            text: faq.modelData.body; color: Theme.muted; lineHeight: 1.3
            opacity: faq.open ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        }
    }

    // Section heading with one quiet line under it.
    component SectionHead: ColumnLayout {
        property alias title: headText.text
        property alias intro: introText.text
        Layout.fillWidth: true; spacing: 4
        Copy { id: headText; font.pixelSize: Theme.heading; font.weight: Theme.strong; Layout.fillWidth: true }
        Copy { id: introText; visible: text !== ""; color: Theme.muted; font.pixelSize: Theme.small; Layout.fillWidth: true }
    }

    Item {
        id: frame
        width: Math.min(parent.width - 48, 1240); height: parent.height; x: (parent.width - width) / 2

        ColumnLayout {
            id: nav
            width: 184; y: 16; spacing: 4
            RowLayout {
                Layout.fillWidth: true; Layout.bottomMargin: 14; spacing: 10
                IconButton {
                    iconKind: "back"; implicitWidth: 32; implicitHeight: 32; Layout.leftMargin: -6
                    onClicked: backend.back()
                    ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("back"); Accessible.name: win.tr("back")
                }
                Copy { text: win.tr("help"); font.pixelSize: Theme.display; font.weight: Theme.strong; wrapMode: Text.NoWrap }
            }
            Repeater {
                model: page.groups
                AbstractButton {
                    id: navItem
                    required property var modelData
                    required property int index
                    readonly property bool current: index === page.currentGroup
                    Layout.fillWidth: true; implicitHeight: 36; hoverEnabled: true
                    Accessible.name: modelData.label
                    onClicked: { scrollTo.stop(); scrollTo.to = flick.topOf(modelData.block); scrollTo.start() }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: 8
                        color: navItem.current ? Theme.accentSoft : navItem.hovered ? Theme.raised : Theme.clear(Theme.raised)
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        Rectangle {
                            visible: navItem.current; width: 3; height: 16; radius: 1.5; color: Theme.accent
                            anchors.left: parent.left; anchors.leftMargin: 4; anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                    contentItem: Copy {
                        leftPadding: 16; text: navItem.modelData.label; wrapMode: Text.NoWrap; elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        color: navItem.current ? Theme.accentText : navItem.hovered ? Theme.text : Theme.sub
                        font.weight: navItem.current ? Font.DemiBold : Font.Normal
                    }
                }
            }
        }

        Flickable {
            id: flick
            function topOf(block) { return Math.max(0, Math.min(block.y - 8, contentHeight - height)) }
            x: nav.width + 36; width: frame.width - x; height: frame.height; clip: true
            contentWidth: width; contentHeight: column.implicitHeight + 48
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: SlimScrollBar {}
            NumberAnimation on contentY { id: scrollTo; running: false; duration: Theme.normal; easing.type: Easing.OutCubic }

            ColumnLayout {
                id: column
                width: Math.min(flick.width - 20, 820); y: 16
                spacing: 32

                ColumnLayout {
                    id: guideBlock; Layout.fillWidth: true; spacing: 12
                    SectionHead { title: win.tr("helpGuide"); intro: win.tr("helpGuideIntro") }
                    SettingGroup { Repeater { model: page.help.guide || []; delegate: StepRow {} } }
                }

                ColumnLayout {
                    id: tipsBlock; Layout.fillWidth: true; spacing: 12
                    SectionHead { title: win.tr("tips"); intro: win.tr("helpTipsIntro") }
                    SettingGroup {
                        Repeater {
                            model: page.help.tips || []
                            SettingRow { required property var modelData; required property int index; first: index === 0; title: modelData.title; hint: modelData.body }
                        }
                    }
                }

                ColumnLayout {
                    id: faqBlock; Layout.fillWidth: true; spacing: 12
                    SectionHead { title: win.tr("helpFaq"); intro: win.tr("helpFaqIntro") }
                    SettingGroup { Repeater { model: page.help.faq || []; delegate: FaqRow {} } }
                }

                ColumnLayout {
                    id: troubleshootBlock; Layout.fillWidth: true; spacing: 12
                    SectionHead { title: win.tr("helpTroubleshoot"); intro: win.tr("helpTroubleshootIntro") }
                    SettingGroup { Repeater { model: page.help.troubleshoot || []; delegate: StepRow {} } }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("environment"); hint: backend.diagnosticsSummary
                            ActionButton {
                                id: copyButton
                                property bool done: false
                                text: done ? win.tr("copiedDiagnostics") : win.tr("copyDiagnostics")
                                onClicked: { backend.copyDiagnostics(); done = true; copiedTimer.restart() }
                                Timer { id: copiedTimer; interval: 1600; onTriggered: copyButton.done = false }
                            }
                            ActionButton { text: win.tr("checkTools"); ghost: true; enabled: !win.appView.working; onClicked: backend.checkTools() }
                        }
                        SettingRow {
                            title: win.tr("logFolder"); hint: "%USERPROFILE%\\.disc_splitter\\logs"
                            ActionButton { text: win.tr("openLogFolder"); onClicked: backend.openLogFolder() }
                        }
                        SettingRow {
                            title: win.tr("feedback"); hint: win.tr("feedbackHint")
                            ActionButton {
                                text: win.tr("report"); rightPadding: 20; implicitWidth: contentItem.implicitWidth + 52
                                onClicked: backend.help("report")
                                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("opensBrowser")
                                Icon { kind: "external"; ink: Theme.muted; width: 12; height: 12; anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; anchors.rightMargin: 12 }
                            }
                        }
                    }
                }

                ColumnLayout {
                    id: aboutBlock; Layout.fillWidth: true; spacing: 12
                    SectionHead { title: win.tr("aboutApp") }
                    SettingGroup {
                        Rectangle {
                            Layout.fillWidth: true; implicitHeight: 92; color: "transparent"
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 14
                                Image {
                                    source: "images/logo.png"; mipmap: true
                                    Layout.preferredWidth: 56; Layout.preferredHeight: 56; fillMode: Image.PreserveAspectFit; smooth: true
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 3
                                    Copy { text: "DiscSplitter"; font.pixelSize: Theme.title; font.weight: Theme.strong }
                                    Copy { text: win.tr("aboutTagline"); color: Theme.muted; Layout.fillWidth: true }
                                    Copy { text: win.tr("versionLabel") + " " + backend.appVersion; color: Theme.faint; font.pixelSize: Theme.small; font.family: Theme.mono }
                                }
                                ActionButton {
                                    id: versionButton
                                    property bool done: false
                                    text: done ? win.tr("copiedDiagnostics") : win.tr("copyVersion"); ghost: true
                                    onClicked: { backend.copyText("DiscSplitter " + backend.appVersion); done = true; versionTimer.restart() }
                                    Timer { id: versionTimer; interval: 1600; onTriggered: versionButton.done = false }
                                }
                            }
                        }
                        SettingRow {
                            title: win.tr("projectHome"); hint: backend.repository
                            ActionButton {
                                text: "GitHub"; rightPadding: 20; implicitWidth: contentItem.implicitWidth + 52
                                onClicked: backend.help("readme")
                                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: win.tr("opensBrowser")
                                Icon { kind: "external"; ink: Theme.muted; width: 12; height: 12; anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; anchors.rightMargin: 12 }
                            }
                        }
                        SettingRow { title: win.tr("license"); hint: win.tr("licenseText") }
                        SettingRow { title: win.tr("credits"); hint: win.tr("creditsText") }
                    }
                }
            }
        }
    }
}
