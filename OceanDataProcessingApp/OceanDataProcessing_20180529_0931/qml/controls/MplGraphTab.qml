import QtQuick 2.7
import QtQuick.Controls 1.4
import MplBackend 1.0

Tab {
    active: true
    property string objName: ""
    MplFigureCanvas {
        objectName: objName
    }
}