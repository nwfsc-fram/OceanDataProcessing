import QtQuick 2.5
import QtQuick.Controls 1.5
import QtQuick.Layouts 1.1
import QtQuick.Controls.Styles 1.4
import QtQuick.Controls.Private 1.0

Item {
    id: itmBin

    property int folderWidth: 600

    Connections {
        target: settings
        onVesselInstrumentChanged: changeVesselInstrument()
    } // settings.onVesselChanged

    function changeVesselInstrument() {

    }

    ColumnLayout {
        id: clBin
        anchors.left: parent.left
        anchors.leftMargin: 20
        anchors.top: parent.top
        anchors.topMargin: 30
//        anchors.bottom: parent.bottom
//        anchors.bottomMargin: 20
        spacing: 20
        RowLayout {
            id: glFolders
            spacing: 20
            Label { text: qsTr("Output Folder Name") }
            TextField {
                id: tfOutputFolder
                text: settings.binnedPath ? settings.binnedPath : ""
                enabled: true
                Layout.preferredWidth: folderWidth
            } // tfOutputFolder
        } // glFolders
        RowLayout {
            id: rlBinDetails
            spacing: 40
            RowLayout {
                spacing: 10
                Label { text: qsTr("Select Bin Variable") }
                ComboBox {
                    id: cbBinVariable
                    model: ["Depth (m)", "Temperature (degC)"]
                    Layout.preferredWidth: 200
                } // cbBinVariable
            }
            RowLayout {
                spacing: 10
                Label { text: qsTr("Bin Size") }
                TextField {
                    id: tfBinSize;
                    text: qsTr("1");
                    validator: IntValidator {bottom: 1; top: 1000}
                    Layout.preferredWidth: 60
                } // tfBinSize
                Label { text: qsTr("m") }
            }
            RowLayout {
                spacing: 10
                Label { text: qsTr("Average ?") }
                Switch { id: swAverage; checked: true }
            }

            Button {
                id: btnProcess;
                text: qsTr("Process");
                Layout.preferredWidth: 80
                Layout.preferredHeight: 40
                onClicked: {
                    binScreen.binFiles(tfOutputFolder.text, cbBinVariable.currentText,
                                       parseInt(tfBinSize.text), swAverage.checked)

                }
            }
        }
    }
    TableView {
        id: tbCasts
        anchors.top: clBin.bottom
        anchors.topMargin: 20
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        anchors.left: parent.left
        anchors.leftMargin: 20
        anchors.right: parent.right
        anchors.rightMargin: 20
        selectionMode: SelectionMode.ExtendedSelection
        model: binScreen.filesModel
        TableViewColumn {
            id: tvcSource
            title: "Source Cast File"
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
            title: "Output Binned CSV File"
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
            title: "Date/Time of Binning"
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
            width: 310
            delegate: Text {
                text: styleData.value ? styleData.value : ""
                color: styleData.textColor
                elide: styleData.elideMode
                renderType: Text.NativeRendering
            }
        } // status
    } // tbCasts
}
