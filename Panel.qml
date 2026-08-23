import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// THESIS: Prayer time should read like a precise daily timetable, not a terminal tooltip.
// OWN-WORLD: Omarchy popup colors, typography, spacing, borders, and one authored monochrome mark.
// STORY: See the next prayer, verify location, scan every time and remaining interval, adjust settings if needed.
// FIRST VIEWPORT: Next-prayer header, location/date rail, six aligned schedule rows, method footer.
// FORM: Theme-native operational ledger; openathan-ledger-v1.
// FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md.
Panel {
  id: root
  moduleName: "bredda.openathan"
  ipcTarget: "bredda.openathan"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.5)
  readonly property color accent: Style.selectedStateColor(foreground, Color.accent)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string home: Quickshell.env("HOME") || ""
  readonly property string scriptPath: home + "/.config/omarchy/plugins/bredda.openathan/openathan.py"

  property var report: null
  property string errorText: ""
  property bool loading: false
  property int iconRevision: 0

  readonly property var nextPrayer: report && report.next ? report.next : null
  readonly property var prayers: report && report.prayers ? report.prayers : []
  readonly property string barLabel: nextPrayer
    ? nextPrayer.name + " · " + nextPrayer.countdown
    : (loading ? "Prayer …" : "Prayer unavailable")
  readonly property string themedIconSource: report && report.iconPath
    ? "file://" + report.iconPath + "?v=" + iconRevision
    : Qt.resolvedUrl("assets/openathan.svg")

  function settingArgs() {
    var args = ["python3", root.scriptPath]
    args.push("--location-mode", String(setting("locationMode", "Auto")).toLowerCase())
    args.push("--city", String(setting("manualCity", "")))
    args.push("--country", String(setting("manualCountry", "")))
    args.push("--method", String(setting("calculationMethod", "Auto")))
    args.push("--school", String(setting("asrSchool", "Shafi")))
    if (setting("notificationsEnabled", true) === true) args.push("--notify")
    return args
  }

  function refresh() {
    if (dataProc.running) return
    loading = report === null
    dataProc.command = settingArgs()
    dataProc.running = true
  }

  function open() {
    root.controller.show()
    root.refresh()
  }

  function close() { root.controller.hide() }
  function toggle() { root.opened ? root.close() : root.open() }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  Process {
    id: dataProc
    onExited: function(exitCode) {
      root.loading = false
      if (exitCode !== 0 && root.report === null && root.errorText === "")
        root.errorText = "Prayer data could not be loaded. Check your connection or location settings."
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var raw = String(text || "").trim()
        if (!raw) return
        try {
          var parsed = JSON.parse(raw)
          if (parsed.ok === false) {
            root.errorText = String(parsed.error || "Prayer data is unavailable.")
            return
          }
          root.report = parsed
          root.errorText = ""
          root.iconRevision++
        } catch (e) {
          root.errorText = "OpenAthan returned an unreadable response."
        }
      }
    }
  }

  Timer {
    interval: 30000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(440))
    contentHeight: panel.fittedContentHeight(contentColumn.implicitHeight, Style.space(620))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onActivateRequested: root.refresh()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "r" || t === "R") root.refresh() }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: contentColumn
          width: parent.width
          spacing: Style.space(12)

          Item {
            width: parent.width
            implicitHeight: Math.max(mark.height, heroLabels.implicitHeight, nextTime.implicitHeight)

            Image {
              id: mark
              width: Style.space(42)
              height: width
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              source: root.themedIconSource
              fillMode: Image.PreserveAspectFit
              smooth: true
            }

            Column {
              id: heroLabels
              anchors.left: mark.right
              anchors.leftMargin: Style.space(14)
              anchors.right: nextTime.left
              anchors.rightMargin: Style.space(14)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                width: parent.width
                text: root.nextPrayer ? root.nextPrayer.name : (root.loading ? "Finding prayer times" : "Prayer times unavailable")
                textFormat: Text.PlainText
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.heading
                font.bold: true
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                text: root.nextPrayer ? (root.nextPrayer.dayLabel + " · " + root.nextPrayer.countdown) : ""
                textFormat: Text.PlainText
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
              }
            }

            Text {
              id: nextTime
              width: Style.space(68)
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: root.nextPrayer ? root.nextPrayer.time : "—"
              textFormat: Text.PlainText
              color: root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.heading
              font.bold: true
              horizontalAlignment: Text.AlignRight
            }
          }

          Item {
            visible: !!root.report
            width: parent.width
            implicitHeight: Math.max(locationText.implicitHeight, dateText.implicitHeight) + Style.space(10)

            Rectangle {
              anchors.fill: parent
              radius: Style.cornerRadius
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.05)
            }

            Text {
              id: locationText
              anchors.left: parent.left
              anchors.leftMargin: Style.space(10)
              anchors.right: dateText.left
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: root.report ? "󰍎  " + root.report.location.label : ""
              textFormat: Text.PlainText
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }

            Text {
              id: dateText
              anchors.right: parent.right
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: root.report ? root.report.hijri : ""
              textFormat: Text.PlainText
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          PanelSeparator { foreground: root.foreground }

          Column {
            visible: root.prayers.length > 0
            width: parent.width
            spacing: Style.space(3)

            Repeater {
              model: root.prayers

              Rectangle {
                required property var modelData
                width: parent.width
                height: Style.space(42)
                radius: Style.cornerRadius
                color: modelData.status === "next"
                  ? Style.selectedFillFor(root.foreground, Color.accent)
                  : "transparent"

                Rectangle {
                  visible: parent.modelData.status === "next"
                  anchors.left: parent.left
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.spacing.hairline
                  height: parent.height - Style.space(12)
                  color: root.accent
                }

                Text {
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(10)
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(100)
                  text: parent.modelData.name
                  textFormat: Text.PlainText
                  color: parent.modelData.key === "sunrise" ? root.dim : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: parent.modelData.status === "next"
                }

                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  anchors.verticalCenter: parent.verticalCenter
                  text: parent.modelData.time
                  textFormat: Text.PlainText
                  color: parent.modelData.status === "next" ? root.accent : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                }

                Text {
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(10)
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(116)
                  horizontalAlignment: Text.AlignRight
                  text: parent.modelData.relative
                  textFormat: Text.PlainText
                  color: parent.modelData.status === "next" ? root.foreground : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
              }
            }
          }

          Text {
            visible: root.errorText !== ""
            width: parent.width
            topPadding: Style.space(18)
            bottomPadding: Style.space(18)
            text: root.errorText
            textFormat: Text.PlainText
            color: Color.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
          }

          PanelSeparator { visible: !!root.report; foreground: root.foreground }

          Item {
            visible: !!root.report
            width: parent.width
            implicitHeight: Math.max(methodText.implicitHeight, sourceText.implicitHeight)

            Text {
              id: methodText
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              text: root.report ? root.report.method.label + " · " + root.report.school : ""
              textFormat: Text.PlainText
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            Text {
              id: sourceText
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: root.report
                ? ((root.report.stale || root.report.location.stale)
                  ? "CACHED DATA"
                  : (root.report.location.source === "auto" ? "AUTO LOCATION" : "MANUAL LOCATION"))
                : ""
              textFormat: Text.PlainText
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1
            }
          }
        }
      }
    }
  }
}
