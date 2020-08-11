import QtQuick 2.7
import QtQuick.Controls 1.5
//import QtQuick.Controls 2.2
import QtQuick.Layouts 1.1
import QtQuick.Controls.Styles 1.4
import QtQuick.Controls.Private 1.0

Item {

    property int folderWidth: 600

    Connections {
        target: settings
        onVesselInstrumentChanged: changeVesselInstrument()
    } // settings.onVesselChanged
//    Connections {
//        target: settings
//        onInstrumentChanged: changeInstrument(instrument)
//    } // settings.onInstrumentChanged

    Component.onCompleted: {
        settings.instrument = "CTD";
    }

    function changeVesselInstrument() {

        var value = (main.cbVessel.text === "Select Vessel") ? false : true;

        console.info('changeVesselInstrument, Select Vessel? = ' + value);

        btnConvertAll.enabled = value;
        btnConvertMissing.enabled = value;

        return;

//        convertScreen.filesModel.clear()
        if (main.cbVessel.text === "Select Vessel") {
//            settings.rawPath = "";
//            settings.convertedPath = "";
//            settings.locationsPath = "";
            btnConvertAll.enabled = false;
            btnConvertMissing.enabled = false;
        } else {
            btnConvertAll.enabled = true;
            btnConvertMissing.enabled = true;
        }

    }

//    function changeVessel(vessel) {
//        convertScreen.filesModel.clear()
//        if (vessel === "Select Vessel") {
//            settings.rawPath = "";
//            settings.convertedPath = "";
//            settings.locationsPath = "";
//            btnConvertAll.enabled = false;
//            btnConvertMissing.enabled = false;
//        } else {
//            btnConvertAll.enabled = true;
//            btnConvertMissing.enabled = true;
//        }
//    }

    RowLayout {
        id: rlSetup
        anchors.left: parent.left
        anchors.leftMargin: 20
        anchors.top: parent.top
        anchors.topMargin: 10
        spacing: 20
        GridLayout {
            id: glFolders
//            x: 20
//            y: 20
            rows: 2
            columns: 2
            rowSpacing: 20
            columnSpacing: 20
            Label { text: qsTr("Source Folder Name") }
            TextField {
                text: settings.rawPath ? settings.rawPath : ""
                enabled: true
                Layout.preferredWidth: folderWidth
                Layout.preferredHeight: 24
            }
            Label { text: qsTr("Output Folder Name") }
            TextField {
                text: settings.convertedPath ? settings.convertedPath : ""
                enabled: true
                Layout.preferredWidth: folderWidth
            }
            Label { text: qsTr("Coordinates File") }
            TextField {
                id: tfLocationsFile
                text: settings.locationsPath ? settings.locationsPath : ""
                enabled: true
                Layout.preferredWidth: folderWidth
            }
        } // glFolders
        Button {
            id: btnHexCnv
            text: "Source Type:\n" + settings.sourceType.toUpperCase();
    //        anchors.left: glFolders.right
    //        anchors.leftMargin: 30
//            anchors.verticalCenter: glFolders.verticalCenter
//            anchors.horizontalCenter: glFolders.horizontalCenter
            Layout.preferredHeight: 40
            Layout.preferredWidth: 100
            checkable: true
            checked: false
            onClicked: {
                console.info(settings.instrument + ', ' + settings.sourceType);

                if (settings.instrument === "CTD") {
                    if (settings.sourceType === "hex") {
                        settings.sourceType = "cnv";
                    } else if (settings.sourceType === "cnv") {
                        settings.sourceType = "csv";
                    } else {
                        settings.sourceType = "hex";
                    }
                } else if (settings.instrument === "UCTD") {
                    settings.sourceType = "asc";
                } else if (settings.instrument === "SBE39") {
                    settings.sourceType = "asc";
                }
            }
        } // btnHexCnv
        ColumnLayout {
            id: clConvert
            anchors.verticalCenter: glFolders.verticalCenter
            Button {
                id: btnConvertSelected
                Layout.preferredHeight: 40
                Layout.preferredWidth: 100
                enabled: tbCasts.selection.count > 0 ? true : false
                text: qsTr("Convert Selected")
                onClicked: {
                    var indices = [];
                    tbCasts.selection.forEach( function(rowIndex) {
                        indices.push(rowIndex);
                    })
                    convertScreen.convertSelected(settings.sourceType,
                        tfLocationsFile.text, indices);
                }
            } // btnConvertSelected
            Button {
                id: btnConvertMissing
                Layout.preferredHeight: 40
                Layout.preferredWidth: 100
                enabled: false
                text: qsTr("Convert Missing")
                onClicked: {
                    convertScreen.convertMissing(settings.sourceType, tfLocationsFile.text);
                }
            } // btnConvertMissing
            Button {
                id: btnConvertAll
                Layout.preferredHeight: 40
                Layout.preferredWidth: 100
                enabled: false
                text: qsTr("Convert All")
                onClicked: {
                    convertScreen.convertAll(settings.sourceType, tfLocationsFile.text);
                }
            } // btnConvertAll
        } // clConvert
    }
    TableView {
        id: tbCasts
        anchors.top: rlSetup.bottom
        anchors.topMargin: 20
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        anchors.left: parent.left
        anchors.leftMargin: 20
        anchors.right: parent.right
        anchors.rightMargin: 20
        selectionMode: SelectionMode.ExtendedSelection
        model: convertScreen.filesModel
//        TableViewColumn {
//            title: "Process?"
//            role: "process"
//            width: 80
//            delegate: Text {
//                text: styleData.value ? styleData.value : ""
//                color: styleData.textColor
//                elide: styleData.elideMode
//                renderType: Text.NativeRendering
//            }
//        } // process
        TableViewColumn {
            id: tvcSource
            title: "Source " + settings.sourceType.toUpperCase() + " File"
            role: "source"
            width: 200
            delegate: Text {
                text: styleData.value ? styleData.value.replace(/^.*[\\\/]/, '') : ""
                color: styleData.textColor
                elide: styleData.elideMode
                renderType: Text.NativeRendering
            }
        } // source
        TableViewColumn {
            title: "Output CSV File"
            role: "output"
            width: 200
            delegate: Text {
                text: styleData.value ? styleData.value : ""
                color: styleData.textColor
                elide: styleData.elideMode
                renderType: Text.NativeRendering
            }
        } // output
        TableViewColumn {
            title: "Date/Time of Conversion"
            role: "dateTime"
            width: 200
            delegate: Text {
                text: styleData.value ? styleData.value : ""
                color: styleData.textColor
                elide: styleData.elideMode
                renderType: Text.NativeRendering
            }
        } // dateTime
        TableViewColumn {
            title: "Status"
            role: "status"
            width: 300
            delegate: Text {
                text: styleData.value ? styleData.value : ""
                color: styleData.textColor
                elide: styleData.elideMode
                renderType: Text.NativeRendering
            }
        } // status
    } // tbCasts
}