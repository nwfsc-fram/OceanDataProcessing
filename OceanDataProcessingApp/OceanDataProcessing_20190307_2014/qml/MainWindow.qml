import QtQuick 2.5
import QtQuick.Controls 1.2
import QtQuick.Layouts 1.2
import QtQuick.Window 2.2
import QtQuick.Dialogs 1.2

//import py.trawl.WindowFrameSize 1.0
//import "../common"

import "screens"
import "statemachine"
//import "controls"
//import "codebehind"
//import "dialogs"

ApplicationWindow {
    id: main
    title: qsTr("Oceanographic Data Processing")
    width: 1008 //1024     // 1040 with borders - 16 > 1008
    height: 730 //768     // 806 with titlebar+borders - 38 > 730
    visible: true
    property alias sbMsg: sbMsg

    property alias cbSurvey: cbSurvey
    property alias cbVessel: cbVessel
    property alias cbInstrument: cbInstrument

    signal keyPressed(string action);

//    opacity: 1.0
//    flags: Qt.Desktop
//    flags: Qt.Widget

//    Connections {
//        target: graphScreen
//        onCursorMoved: updateStatusBar(x, y)
//    }
//
//    function updateStatusBar(x, y) {
//        sbMsg.
//    }

    onClosing: {
//        messageDialog.show("CLOSING...");
//        console.info('stopping all threads, application is closing')
//        fpcMain.stop_all_threads();
        graphScreen.savePickleFile();
        settings.stop_all_threads();
    }

//    function displaySeriesChanged() {
//        if (timeSeries.displaySeries) {
//
//        }
//    }

//    signal vesselChanged(string vessel);
//    signal instrumentChanged(string instrument);

    function resetHauls(status) {
        settings.haul = null;
        timeSeries.stopLoadingTimeSeries();
        timeSeries.haulsModel.populate_model();
        cbHaul.currentIndex = 0;
    }

    function passwordFailed() {
        dlgOkay.message = "Your authentication failed\n\nPlease try again"
        dlgOkay.open()
    }

    menuBar: MenuBar {
        Menu {
            title: "File"
            MenuItem {
                text: "Exit"
                onTriggered: Qt.quit();
            }
        }
    }
    toolBar:ToolBar {
        RowLayout {
            anchors.fill: parent

            ExclusiveGroup {
                id: egToolButtons
            }

            ToolButton {
                id: btnConvert
                iconSource: "qrc:/resources/images/convert.png"
//                enabled: settings.loggedInStatus
                tooltip: "Convert hex to csv"
                checked: true
                checkable: true
                exclusiveGroup: egToolButtons
                onClicked: {
                    tvScreens.currentIndex = 0;
                }
            } // btnConvert
            ToolButton {
                id: btnGraph
                iconSource: "qrc:/resources/images/graph.png"
//                enabled: settings.loggedInStatus
                tooltip: "QA/QC Graphs"
                checked: false
                checkable: true
                exclusiveGroup: egToolButtons
                onClicked: {
                    tvScreens.currentIndex = 1;
                }
            } // btnGraph
            ToolButton {
                id: btnBin
                iconSource: "qrc:/resources/images/bin.png"
//                enabled: settings.loggedInStatus
                tooltip: "Finalize & Bin Data"
                checked: false
                checkable: true
                exclusiveGroup: egToolButtons
                onClicked: {
                    tvScreens.currentIndex = 2;
                }
            } // btnBin

            Item { Layout.preferredWidth: 20 }

            ToolButton {
                id: btnSettings
                iconSource: "qrc:/resources/images/settings.png"
                tooltip: "Settings"
            } // btnSettings

            Item { Layout.preferredWidth: 70 }

            Label {
                id: lblSurvey
                text: qsTr("Survey")
                Layout.preferredWidth: 40
            } // lblSurvey
            ComboBox {
                id: cbSurvey
                Layout.preferredWidth: 200
                enabled: true
                model: settings.surveyModel
                currentIndex: 0
                onCurrentIndexChanged: {
                    if (currentText != "") {
                        settings.changeSurvey(currentText);
                        cbVessel.currentIndex = 0;
                    }
                }
            } // cbSurvey

            Item { Layout.preferredWidth: 20 }

            Label {
                id: lblVessel
                text: qsTr("Vessel")
                Layout.preferredWidth: 40
            } // lblVessel
            ComboBox {
                id: cbVessel
                Layout.preferredWidth: 100
                enabled: true
                model: settings.vesselModel
                currentIndex: 0
                onCurrentIndexChanged: {
                    var values = {"survey": cbSurvey.currentText,
                                  "vessel": currentText,
                                  "instrument": cbInstrument.currentText}
                    settings.changeVesselInstrument(values);
                }
            } // cbVessel

            Item { Layout.preferredWidth: 20 }

            Label {
                id: lblInstrument
                text: qsTr("Instrument")
                Layout.preferredWidth: 60
            } // lblInstrument
            ComboBox {
                id: cbInstrument
                Layout.preferredWidth: 100
                enabled: true
                model: ["CTD", "UCTD"]
                currentIndex: 0
                onCurrentIndexChanged: {
//                    main.instrumentChanged(currentText);
                    settings.instrument = currentText;
                    var values = {"survey": cbSurvey.currentText,
                                  "vessel": cbVessel.currentText,
                                  "instrument": currentText}
                    if (cbVessel.currentText !== "Select Vessel") {
                        settings.changeVesselInstrument(values);
                    }
                }
            } // cbInstrument

//            Item { Layout.preferredWidth: 20 }
            Item { Layout.fillWidth: true }

//            Label {
//                id: lblMode
//                text: qsTr("Test Mode?")
//            } // lblMode
//            Switch {
//                id: swMode
//                checked: true;
//                enabled: !settings.isLoading;
//                onClicked: {
//                    settings.mode = (checked ? "test" : "real");
//                }
//            } // swMode
        }
    }
    TabView {
        id: tvScreens
//        enabled: settings.loggedInStatus
        enabled: true
        anchors.rightMargin: 0
        anchors.bottomMargin: 0
        anchors.leftMargin: 0
        anchors.topMargin: 0
        anchors.fill: parent

        tabsVisible: false

        Keys.onPressed: {
            if (currentIndex === 1) {
                if ((event.key === 90) || (event.key === 65)){
                    // Zoom In
                    graphScreen.keyPressed(settings.graphTab, "zoom in");
                } else if (event.key === 88) {
                    // Zoom Out
                    graphScreen.keyPressed(settings.graphTab, "zoom out");
                }
            }
        }

        Tab {
            id: tabConvert
            title: "Convert"
            active: true
            source: "screens/ConvertScreen.qml"
            onVisibleChanged: settings.statusBarMessage = "";
        } // Convert
        Tab {
            id: tabGraph
            title: "Graph"
            active: true
            source: "screens/GraphScreen.qml"
            onVisibleChanged: settings.statusBarMessage = "";
        } // Graph
        Tab {
            id: tabBin
            title: "Bin"
            active: true
            source: "screens/BinScreen.qml"
            onVisibleChanged: settings.statusBarMessage = "";
        } // Bin
    }
    statusBar: StatusBar {
        id: sbMsg
        Item {
            RowLayout {
                anchors.fill: parent
                Label { text: settings.statusBarMessage }
            }
        }
    }
    MessageDialog {
        id: messageDialog
        width: 600
        height: 800
        objectName: "dlgUnhandledException"
        title: qsTr("Unhandled Exception Occurred")
        icon: StandardIcon.Critical
        function show(caption) {
            messageDialog.text = caption;
            messageDialog.open();
        }
        onAccepted: {
            mainWindow.close();
        }
    }
}
