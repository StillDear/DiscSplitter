import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
// One scrolling page with only the settings a user can actually change.
Item {
    id: page
    required property var win
    property string section: "appearance"
    readonly property var presets: ["#F2A33A", "#60CDFF", "#B9A5FF", "#4FD1C5"]
    // Example filename for the selected preset, e.g. "03 - Song Title.flac".
    function example(key) {
        const title = win.tr("tplSongTitle"), ext = win.discView.outputFormat === "flac" ? ".flac" : ".mkv"
        const name = key === "nn_title" ? "03 - " + title : key === "nn_dot_title" ? "03. " + title
                   : key === "artist_title" ? win.tr("tplSongArtist") + " - " + title : title
        return name + ext
    }
    ColorDialog {
        id: colorDialog
        title: win.tr("accent")
        selectedColor: Theme.accent
        onAccepted: backend.setPreference("accent", String(selectedColor))
    }
    // Kept for the smoke runner: scrolls the requested group into view.
    onSectionChanged: {
        const target = section === "tools" ? toolsBlock : section === "files" ? outputBlock
                     : section === "matching" ? matchingBlock : section === "online" ? onlineBlock : null
        flick.contentY = target ? flick.topOf(target) : 0
    }
    // Section list on the left (stays put), the settings themselves use the rest of the width.
    readonly property var groups: [
        { key: "appearance", label: win.tr("appearanceShort"), block: appearanceBlock },
        { key: "files", label: win.tr("outputSection"), block: outputBlock },
        { key: "matching", label: win.tr("matching"), block: matchingBlock },
        { key: "preview", label: win.tr("previewSection"), block: previewBlock },
        { key: "online", label: win.tr("onlineSection"), block: onlineBlock },
        { key: "tools", label: win.tr("tools"), block: toolsBlock }]
    // The group being read: the last one whose heading has scrolled to the top (the last one at the very end).
    readonly property int currentGroup: {
        const y = flick.contentY
        if (y >= flick.contentHeight - flick.height - 2 && y > 0) return groups.length - 1
        let found = 0
        for (let i = 0; i < groups.length; i++) if (groups[i].block.y - 24 <= y) found = i
        return found
    }

    Item {
        id: frame
        width: Math.min(parent.width - 48, 1240); height: parent.height; x: (parent.width - width) / 2

        ColumnLayout {
            id: nav
            width: 184; y: 16; spacing: 4
            Copy { text: win.tr("settings"); font.pixelSize: Theme.px(20); font.bold: true; Layout.bottomMargin: 14 }
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
                        color: navItem.current ? Theme.accentSoft : navItem.hovered ? Theme.raised : "transparent"
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
            ScrollBar.vertical: SlimScrollBar { id: settingsBar }
            NumberAnimation on contentY { id: scrollTo; running: false; duration: Theme.normal; easing.type: Easing.OutCubic }

            ColumnLayout {
                id: column
                width: flick.width - 20; y: 16
                spacing: 28

                // Appearance
                ColumnLayout {
                    id: appearanceBlock; Layout.fillWidth: true; spacing: 10
                    Copy { text: win.tr("appearanceShort"); font.pixelSize: Theme.px(15); font.weight: Font.DemiBold }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("theme")
                            Segmented {
                                options: [{ key: "dark", label: win.tr("dark") }, { key: "light", label: win.tr("light") }, { key: "system", label: win.tr("system") }]
                                current: backend.config.theme
                                onPicked: function(key) { backend.setPreference("theme", key) }
                            }
                        }
                        SettingRow {
                            id: accentRow
                            readonly property string current: String(backend.config.accent)
                            readonly property bool preset: page.presets.indexOf(current.toUpperCase()) >= 0
                            title: win.tr("accent")
                            hint: current === "system" ? win.tr("accentSystemHint")
                                : preset ? ""
                                : win.fmt("accentCustomHint", { c: current.toUpperCase() })
                            Repeater {
                                model: page.presets.concat(["system"])
                                Rectangle {
                                    id: swatch
                                    required property string modelData
                                    readonly property bool on: String(backend.config.accent).toUpperCase() === modelData.toUpperCase()
                                    Layout.preferredWidth: 26; Layout.preferredHeight: 26; radius: 13
                                    scale: swatchArea.containsMouse ? 1.12 : 1
                                    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
                                    Layout.leftMargin: modelData === "system" ? 10 : 0
                                    color: modelData === "system" ? (backend.view.systemAccent || "#60CDFF") : modelData
                                    border.width: on ? 2 : 0; border.color: Theme.text
                                    Rectangle { anchors.fill: parent; anchors.margins: -4; radius: 17; color: "transparent"; border.color: swatch.on ? Theme.line2 : "transparent" }
                                    // Windows swatch: small window glyph so it reads as "follow system"
                                    Rectangle { visible: swatch.modelData === "system"; anchors.centerIn: parent; width: 10; height: 8; radius: 1; color: "transparent"; border.color: "#FFFFFF"; border.width: 1.5 }
                                    MouseArea {
                                        id: swatchArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: backend.setPreference("accent", swatch.modelData)
                                    }
                                    ToolTip.visible: swatchArea.containsMouse; ToolTip.text: swatch.modelData === "system" ? win.tr("accentWindows") : swatch.modelData
                                }
                            }
                            ActionButton { text: win.tr("accentCustom"); selected: !accentRow.preset && accentRow.current !== "system"; implicitHeight: 28; Layout.leftMargin: 6; onClicked: colorDialog.open() }
                        }
                        SettingRow {
                            title: win.tr("uiScale"); hint: win.fmt("uiScaleHint", { p: win.appView.systemScale || 100 })
                            Badge { visible: String(backend.config.interface_scale || "system") !== String(win.appView.startScale || "system"); tone: "accent"; text: win.tr("restartNeeded") }
                            Segmented {
                                options: [{ key: "system", label: win.tr("scaleSystem") }, { key: "1", label: "100%" }, { key: "1.25", label: "125%" },
                                          { key: "1.5", label: "150%" }, { key: "1.75", label: "175%" }]
                                current: String(backend.config.interface_scale || "system")
                                onPicked: function(key) { backend.setPreference("interface_scale", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("fontScale")
                            Segmented {
                                options: [{ key: "0.9", label: win.tr("fontSmall") }, { key: "1", label: win.tr("fontNormal") },
                                          { key: "1.15", label: win.tr("fontLarge") }, { key: "1.3", label: win.tr("fontXLarge") }]
                                current: String(backend.config.font_scale || "1")
                                onPicked: function(key) { backend.setPreference("font_scale", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("density")
                            Segmented {
                                options: [{ key: "comfortable", label: win.tr("comfortable") }, { key: "compact", label: win.tr("compact") }]
                                current: backend.config.density || "comfortable"
                                onPicked: function(key) { backend.setPreference("density", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("motion")
                            Segmented {
                                options: [{ key: "full", label: win.tr("motionFull") }, { key: "reduced", label: win.tr("motionReduced") }]
                                current: backend.config.motion === "reduced" ? "reduced" : "full"
                                onPicked: function(key) { backend.setPreference("motion", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("language")
                            Segmented {
                                options: [{ key: "zh", label: "简体中文" }, { key: "en", label: "English" }]
                                current: backend.config.language
                                onPicked: function(key) { backend.setPreference("language", key) }
                            }
                        }
                    }
                }

                // Output
                ColumnLayout {
                    id: outputBlock; Layout.fillWidth: true; spacing: 10
                    Copy { text: win.tr("outputSection"); font.pixelSize: Theme.px(15); font.weight: Font.DemiBold }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("defaultOutput")
                            hint: win.discView.output || win.tr("notSet")
                            ActionButton { text: win.tr("browse"); enabled: !win.appView.working; onClicked: win.openFolder("output") }
                        }
                    }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("templateLabel")
                            hint: win.fmt("templateHint", { e: page.example(backend.config.filename_template || "title") })
                            Segmented {
                                options: [{ key: "title", label: win.tr("tplTitle") }, { key: "nn_title", label: win.tr("tplNumTitle") },
                                          { key: "nn_dot_title", label: win.tr("tplNumDot") }, { key: "artist_title", label: win.tr("tplArtist") }]
                                current: backend.config.filename_template || "title"
                                onPicked: function(key) { backend.setPreference("filename_template", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("collisionLabel"); hint: win.tr("collisionSettingHint")
                            Segmented {
                                options: [{ key: "ask", label: win.tr("askEveryTime") }, { key: "skip", label: win.tr("skipExisting") },
                                          { key: "overwrite", label: win.tr("overwriteAll") }]
                                current: backend.config.collision_policy || "ask"
                                onPicked: function(key) { backend.setPreference("collision_policy", key) }
                            }
                        }
                    }
                    Copy { text: win.tr("outputRules"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; lineHeight: 1.3 }
                }

                // Title matching
                ColumnLayout {
                    id: matchingBlock; Layout.fillWidth: true; spacing: 10
                    Copy { text: win.tr("matching"); font.pixelSize: Theme.px(15); font.weight: Font.DemiBold }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("chapterLang"); hint: win.tr("chapterLangHint")
                            Segmented {
                                options: [{ key: "first", label: win.tr("langFirst") }, { key: "eng", label: win.tr("langEng") },
                                          { key: "jpn", label: win.tr("langJpn") }, { key: "zho", label: win.tr("langZho") },
                                          { key: "kor", label: win.tr("langKor") }]
                                current: backend.config.chapter_language || "eng"
                                onPicked: function(key) { backend.setPreference("chapter_language", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("toleranceLabel"); hint: win.tr("toleranceHint")
                            Segmented {
                                options: [{ key: "10", label: win.tr("tolStrict") }, { key: "20", label: win.tr("tolNormal") },
                                          { key: "40", label: win.tr("tolLoose") }]
                                current: String(backend.config.duration_tolerance || "20")
                                onPicked: function(key) { backend.setPreference("duration_tolerance", key) }
                            }
                        }
                    }
                }

                // Preview
                ColumnLayout {
                    id: previewBlock; Layout.fillWidth: true; spacing: 10
                    Copy { text: win.tr("previewSection"); font.pixelSize: Theme.px(15); font.weight: Font.DemiBold }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("waveform"); hint: win.tr("waveformSettingHint")
                            Segmented {
                                options: [{ key: "true", label: win.tr("on") }, { key: "false", label: win.tr("off") }]
                                current: backend.config.waveform === false ? "false" : "true"
                                onPicked: function(key) { backend.setPreference("waveform", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("kindColumnSetting"); hint: win.tr("kindColumnSettingHint")
                            Segmented {
                                options: [{ key: "show", label: win.tr("kindColumnShow") }, { key: "auto", label: win.tr("kindColumnAuto") },
                                          { key: "hide", label: win.tr("kindColumnHide") }]
                                current: backend.config.kind_column || "show"
                                onPicked: function(key) { backend.setPreference("kind_column", key) }
                            }
                        }
                    }
                }

                // Online metadata
                ColumnLayout {
                    id: onlineBlock; Layout.fillWidth: true; spacing: 10
                    Copy { text: win.tr("onlineSection"); font.pixelSize: Theme.px(15); font.weight: Font.DemiBold }
                    SettingGroup {
                        SettingRow {
                            first: true; title: win.tr("proxy")
                            Segmented {
                                options: [{ key: "system", label: win.tr("proxySystem") }, { key: "none", label: win.tr("proxyNone") }, { key: "custom", label: win.tr("proxyCustom") }]
                                current: backend.config.proxy_mode || "system"
                                onPicked: function(key) { backend.setPreference("proxy_mode", key) }
                            }
                        }
                        SettingRow {
                            visible: backend.config.proxy_mode === "custom"
                            title: win.tr("proxyUrl"); hint: win.tr("proxyUrlHint")
                            Field {
                                mono: true; Layout.preferredWidth: 260; placeholderText: "127.0.0.1:7890"
                                text: backend.config.proxy_url || ""
                                onEditingFinished: if (text !== (backend.config.proxy_url || "")) backend.setProxyUrl(text)
                            }
                        }
                        SettingRow {
                            title: win.tr("netTest")
                            Repeater {
                                model: win.appView.netTest || []
                                Badge {
                                    required property var modelData
                                    tone: modelData.state === "ok" ? "good" : modelData.state === "running" ? "neutral" : "danger"
                                    text: modelData.label + " · " + (modelData.state === "ok" ? modelData.ms + " ms"
                                          : win.tr(modelData.state === "blocked" ? "netBlocked" : modelData.state === "running" ? "netRunning" : "netError"))
                                    ToolTip.visible: badgeHover.hovered && modelData.detail !== ""; ToolTip.text: modelData.detail
                                    HoverHandler { id: badgeHover }
                                }
                            }
                            ActionButton { text: win.tr("netTestRun"); enabled: !win.appView.working; onClicked: backend.testConnection() }
                        }
                        SettingRow {
                            title: win.tr("netTimeout")
                            Segmented {
                                options: [{ key: "10", label: "10 s" }, { key: "15", label: "15 s" }, { key: "30", label: "30 s" }]
                                current: String(backend.config.net_timeout || "15")
                                onPicked: function(key) { backend.setPreference("net_timeout", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("metaSourceDefault")
                            Segmented {
                                options: [{ key: "itunes", label: "Apple Music" }, { key: "deezer", label: "Deezer" }, { key: "musicbrainz", label: "MusicBrainz" }, { key: "discogs", label: "Discogs" }]
                                current: backend.config.meta_source || "musicbrainz"
                                onPicked: function(key) { backend.setPreference("meta_source", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("discogsToken"); hint: win.tr("discogsTokenHint")
                            Field {
                                mono: true; Layout.preferredWidth: 220; echoMode: TextInput.PasswordEchoOnEdit
                                text: backend.config.discogs_token || ""; placeholderText: "token"
                                onEditingFinished: if (text !== (backend.config.discogs_token || "")) backend.setDiscogsToken(text)
                            }
                            ActionButton { text: win.tr("getToken"); ghost: true; onClicked: Qt.openUrlExternally("https://www.discogs.com/settings/developers") }
                        }
                        SettingRow {
                            title: win.tr("itunesCountry"); hint: win.tr("itunesCountryHint")
                            Segmented {
                                options: ["US", "CN", "JP", "HK", "TW", "GB"].map(function(c) { return { key: c, label: win.tr("country" + c) } })
                                current: backend.config.itunes_country || "US"
                                onPicked: function(key) { backend.setPreference("itunes_country", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("coverSize"); hint: win.tr("coverSizeHint")
                            Segmented {
                                options: [{ key: "standard", label: win.tr("coverStandard") }, { key: "large", label: win.tr("coverLarge") }, { key: "original", label: win.tr("coverOriginal") }]
                                current: backend.config.cover_size || "large"
                                onPicked: function(key) { backend.setPreference("cover_size", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("coverTarget"); hint: win.tr("coverTargetHint")
                            Segmented {
                                options: [{ key: "both", label: win.tr("coverBoth") }, { key: "embed", label: win.tr("coverEmbed") }, { key: "folder", label: win.tr("coverFolder") }]
                                current: backend.config.cover_target || "both"
                                onPicked: function(key) { backend.setPreference("cover_target", key) }
                            }
                        }
                        SettingRow {
                            title: win.tr("autoSearch"); hint: win.tr("autoSearchHint")
                            Item {
                                implicitWidth: 38; implicitHeight: 24
                                Toggle { anchors.verticalCenter: parent.verticalCenter; checked: backend.config.meta_auto_search === true }
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.setPreference("meta_auto_search", backend.config.meta_auto_search === true ? "false" : "true")
                                }
                            }
                        }
                        SettingRow {
                            title: win.tr("coverCache"); hint: win.metaView.coverCache || win.tr("coverCacheEmpty")
                            ActionButton { text: win.tr("clear"); enabled: !!win.metaView.coverCache; onClicked: backend.metadata.clearCoverCache() }
                        }
                    }
                }

                // External tools
                ColumnLayout {
                    id: toolsBlock; Layout.fillWidth: true; spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Copy { text: win.tr("tools"); font.pixelSize: Theme.px(15); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        ActionButton { text: win.tr("checkTools"); ghost: true; enabled: !win.appView.working; onClicked: backend.checkTools() }
                    }
                    SettingGroup {
                        Repeater { model: toolModel; delegate: ToolRow { win: page.win } }
                    }
                    Copy { text: win.tr("toolsIntro"); color: Theme.muted; font.pixelSize: Theme.px(12); Layout.fillWidth: true; lineHeight: 1.3 }
                }

                Copy {
                    text: win.tr("settingsFile") + " · %USERPROFILE%\\.disc_splitter\\settings.json"
                    font.family: Theme.mono; font.pixelSize: Theme.px(11); color: Theme.faint; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere
                }
            }
        }
    }
}
