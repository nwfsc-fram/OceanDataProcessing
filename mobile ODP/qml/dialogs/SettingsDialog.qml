import QtQuick 2.3
import QtQuick.Controls 1.4
import QtQuick.Dialogs 1.2
import QtQuick.Layouts 1.1
import QtQuick.Window 2.0

Dialog {
    id: dlg
    width: 580
    height: 200
//    modality: dialogModal.checked ? Qt.WindowModal : Qt.NonModal
    title: "Settings"

    property alias btnCancel: btnCancel
    property alias btnOkay: btnOkay
    property alias swDeployedSoftware: swDeployedSoftware;

    property string dataPath: "C:\\"
    property bool isDeployed: false

    onRejected: {  }
    onAccepted: {  }
//    onButtonClicked: { console.info("onButtonClicked") }

    contentItem: Rectangle {
//        color: SystemPaletteSingleton.window(true)
        color: "#eee"
        RowLayout {
            id: rlCenterOrDeployed
            spacing: 20
            x: 120
            y: 40
            Label {
                id: lblMessage
//                anchors.horizontalCenter: parent.horizontalCenter
//                horizontalAlignment: Text.AlignHCenter
//                y: 20
    //            anchors.top: lblErrorTitle.bottom
    //            anchors.topMargin: 30
                text: "Deployed Software?"
//                font.pixelSize: 20
            } // lblErrors
            Switch {
                id: swDeployedSoftware
                checked: false
                onClicked: {
                    isDeployed = checked;
                }
            }
        }
        RowLayout {
            id: rlDataPath
            x: rlCenterOrDeployed.x
            anchors.top: rlCenterOrDeployed.bottom
            anchors.topMargin: 40
            spacing: 20
            Label {
                id: lblAction
                text: "Path to Data"
            }
            TextField {
                id: tfDataPath
                placeholderText: "C:\\"
                text: dataPath
                Layout.preferredWidth: 220
            }
            Button {
                id: btnBrowse
                text: "Browse ..."
                onClicked: {
                    console.info('dataPath = ' + settings.dataPath);
                    folderDialog.folder = settings.dataPath;
                    folderDialog.open();
                }
            }
        }
        RowLayout {
            id: rwlButtons
            anchors.horizontalCenter: parent.horizontalCenter
            y: dlg.height - this.height - 20
            spacing: 20
            Button {
                id: btnOkay
                text: "Okay"
                Layout.preferredWidth: this.width
                Layout.preferredHeight: this.height
                onClicked: {
                    settings.dataPath = dataPath;
                    settings.isDeployed = isDeployed;
                    settings.setInstrumentPath();
                    dlg.accept()
                 }
            } // btnOkay
            Button {
                id: btnCancel
                text: "Cancel"
                Layout.preferredWidth: this.width
                Layout.preferredHeight: this.height
                onClicked: { dlg.reject() }
            } // btnCancel
        } // rwlButtons
        FileDialog {
            id: folderDialog
            title: "Please choose a folder"
//            folder: "C:" // shortcuts.home
            selectFolder: true
            onAccepted: {
                console.log("You chose: " + folderDialog.fileUrl);
                dataPath = folderDialog.fileUrl.toString().replace('file:///', '').replace(/[/]/g, '\\');
            }
            onRejected: {
                console.log("Canceled")
            }
        }


//        Keys.onPressed: if (event.key === Qt.Key_R && (event.modifiers & Qt.ControlModifier)) dlg.click(StandardButton.Retry)
        Keys.onEnterPressed: dlg.accept()
        Keys.onReturnPressed: dlg.accept()
        Keys.onEscapePressed: dlg.reject()
        Keys.onBackPressed: dlg.reject() // especially necessary on Android
    }
}
