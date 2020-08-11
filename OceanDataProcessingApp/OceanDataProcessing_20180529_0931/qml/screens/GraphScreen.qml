import QtQuick 2.7
import QtQuick.Controls 2.2
import QtQuick.Controls 1.5
import QtQuick.Layouts 1.2
import QtQuick.Controls.Styles 1.4
import QtQuick.Controls.Private 1.0
import QtQml 2.2
import QtQuick.Extras 1.4
import MplBackend 1.0

import "../statemachine"
import "../controls"

Item {
    id: itmGraph
    objectName: "graphScreen"

    property int buttonSize: 40
    property string lastClick: "cast"
    property variant component: Qt.createComponent("../controls/MplGraphTab.qml");

//    Connections {
//        target: settings
//        onVesselInstrumentChanged: changeVesselInstrument()
//    } // settings.onVesselChanged
//
//    function changeVesselInstrument() {
//
//    }

    function createMplObjects() {
        var graphTitle;
        var mplObjectNames = [];
        var mplObjName;

        for (var i=1; i<=Object.keys(graphScreen.standardGraphs).length; i++) {
            mplObjName = "mplFigure" + i;
            var object = component.createObject(tvGraphs,
                        {"objName": mplObjName, "title": "Graph " + i})
            mplObjectNames.push(mplObjName);
        }
        graphScreen.plotStandardGraphs(mplObjectNames);
    }

    function deleteGraphs() {
        var graphName;
         for (var i=tvGraphs.count-1; i >= 0; i--) {
            graphName = tvGraphs.getTab(i).title
            tvGraphs.removeTab(i);
            graphScreen.deleteGraph(graphName);
        }
    }

//    SplitView {
//        id: svTimeSeries
//        anchors.fill: parent
//        orientation: Qt.Horizontal
//        handleDelegate: Rectangle {
//            width: 10
//            color: "black"
//        }

//        onWidthChanged: {
//            clControlPanel.width = btnMap.checked ? width * 0.5 : width * 0.2;
//        }
//        Rectangle {
    RowLayout {
        anchors.fill: parent
        TableView {
            id: tvCasts
            anchors.top: parent.top
            anchors.bottom: parent.bottom
//                Layout.preferredWidth: 190
//                width: 120
            Layout.preferredWidth: 120
            selectionMode: SelectionMode.ExtendedSelection
            onClicked: {
                if (currentRow !== -1)
                    var cast = model.get(currentRow).cast;
                    tfCast.text = cast;
                    lastClick = "cast";
                    tfX.forceActiveFocus();
                    tfX.selectAll();
                    graphScreen.loadCast(cast);
            }
            model: graphScreen.filesModel
            TableViewColumn {
                title: "Cast"
                role: "cast"
                width: 100
            } // csvFile
        } // tvCasts
        ColumnLayout {
            id: clVariablesPlots
            anchors.top: parent.top
            TableView {
                id: tvVariables
//                    anchors.top: parent.top
//                    anchors.left: tvCasts.right
//                    anchors.leftMargin: 10
                Layout.preferredHeight: 250
//                width: 195
                Layout.preferredWidth: 195
                selectionMode: SelectionMode.ExtendedSelection

//                Layout.preferredWidth: 190
                model: graphScreen.variablesModel
                onClicked: {
                    if (currentRow !== -1) {
                        var variable = model.get(currentRow).variable;
                        if ((lastClick === "cast") || (lastClick === "y")) {
                            tfX.text = variable;
                            lastClick = "x";
                            tfY.forceActiveFocus()
                            tfY.selectAll()
                        } else if (lastClick === "x") {
                            tfY.text = variable;
                            lastClick = "y";
                            tfX.forceActiveFocus();
                            tfX.selectAll()
                        }
                    }
                }
                TableViewColumn {
                    title: "Variable"
                    role: "variable"
                    width: 190
                }
            } // tvVariables
            Label {
                id: lblCast
                text: qsTr("Cast")
            } // lblCast
            TextField {
                id: tfCast
                placeholderText: qsTr("Cast")
                Layout.preferredWidth: 200
                MouseArea {
                    anchors.fill: parent
                    onClicked:{
                        parent.forceActiveFocus();
                        parent.selectAll();
                    }
                }
            } // tfCast
            Label {
                id: lblX
                text: qsTr("X-axis")
            } // lblX
            TextField {
                id: tfX
                placeholderText: qsTr("X-axis")
                Layout.preferredWidth: 200
                MouseArea {
                    anchors.fill: parent
                    onClicked:{
                        parent.forceActiveFocus();
                        parent.selectAll();
                    }
                }
            } // tfX
            Label {
                id: lblY
                text: qsTr("Y-axis")
            } // lblY
            TextField {
                id: tfY
                placeholderText: qsTr("Y-axis")
                Layout.preferredWidth: 200
                MouseArea {
                    anchors.fill: parent
                    onClicked:{
                        parent.forceActiveFocus();
                        parent.selectAll();
//                            parent.cursorPosition = 0;
//                            parent.color = "yellow";
                    }
                }
            } // tfY
            Button {
                id: btnCreatePlot
                text: qsTr("Create Plot")
                enabled: ((graphScreen.isDFLoaded) & (tfX.text !== "") & (tfY.text !== "")) ? true : false
                onClicked: {
                    if ((tfCast.text !== "") & (tfX.text !== "") & (tfY.text !== "")) {

                        // Create the new tab
                        var count = tvGraphs.count + 1;
                        var graphTitle = "Graph " + count;
                        var mplObjName = "mplFigure" + count;
                        var object = component.createObject(tvGraphs,
                                        {"objName": mplObjName, "title": graphTitle})

                        // Plot the Graph
                        graphScreen.plotGraph(graphTitle, mplObjName, tfX.text, tfY.text);
                    }
                }
            } // btnCreatePlot
            Button {
                id: btnAddToPlot
                text: qsTr("Add To Plot")
                enabled: ((graphScreen.isDFLoaded) & (tfX.text !== "") & (tfY.text !== "")) ? true : false
                onClicked: {
                    if ((tfCast.text !== "") & (tfX.text !== "") & (tfY.text !== "")) {

                        // Create the new tab

                        // Plot the Graph
//                        graphScreen.plotGraph(graphTitle, tfCast.text, tfX.text, tfY.text, mplObjName);

                    }
                }
            } // btnAddToPlot
            Button {
                id: btnStandardPlots
                text: qsTr("Standard Plots")
                enabled: graphScreen.isDFLoaded //(tfCast.text !== "") ? true : false
                onClicked: {
                    if (tfCast.text !== "") {

                        var tabCount = tvGraphs.count;
                        var graphCount = Object.keys(graphScreen.standardGraphs).length
                        var diff = graphCount - tabCount;
//                        console.info('tabCount=' + tabCount + ', graphCount=' + graphCount + ', diff=' + diff);
                        var mplObjectNames = [];

                        // Add new tabs as needed
                        for (var i=1; i<=diff; i++) {
                            var mplObjName = "mplFigure" + (tabCount + i).toString();
                            var object = component.createObject(tvGraphs,
                                        {"objName": mplObjName, "title": "Graph " + (tabCount + i).toString()})
                        }

                        // Delete extra tabs
                        for (var i=tabCount; i>graphCount; i--) {
                            console.info('i=' + i);
                            tvGraphs.removeTab(i-1);
                            graphScreen.deleteGraph("Graph " + i);
                        }

                        graphScreen.plotStandardGraphs();

                        return;



                        if (tvGraphs.count > 0) {
                            deleteGraphs();
                        }
                        var graphTitle;
                        var mplObjName;
                        var mplObjectNames = [];

                        for (var i=1; i<=Object.keys(graphScreen.standardGraphs).length; i++) {
                            mplObjName = "mplFigure" + i;
                            var object = component.createObject(tvGraphs,
                                        {"objName": mplObjName, "title": "Graph " + i})
                            mplObjectNames.push(mplObjName);
                        }
                        graphScreen.plotStandardGraphs(mplObjectNames);
                    }
                }
            } // btnStandardPlots
            Button {
                id: btnDeletePlots
                text: qsTr("Delete Plots")
                enabled: tvGraphs.count > 0 ? true : false
                onClicked: {
                    deleteGraphs();
                }
            }// btnDeletePlots
        } // clVariablesPlots
        ColumnLayout {
            id: clMapPanel
            spacing: 10
            RowLayout {
                id: rlTools
//                Layout.fillWidth: true
//                anchors.fill: parent
                ExclusiveGroup { id: egTools }
                ToolButton {
                    id: btnPan
                    iconSource: "qrc:/resources/images/pan.png"
                    enabled: true
                    tooltip: "Pan / Zoom Horizontal"
                    checked: true
                    checkable: true
                    exclusiveGroup: egTools
                    onClicked: {
                        graphScreen.toolMode = "pan";
                    }
                } // btnPan
                ToolButton {
                    id: btnZoomVertical
                    iconSource: "qrc:/resources/images/pan_vertical.png"
                    enabled: true
                    tooltip: "Pan / Zoom Vertical"
                    checked: false
                    checkable: true
                    exclusiveGroup: egTools
                    onClicked: {
                        graphScreen.toolMode = "zoomVertical";
                    }
                } // btnZoomVertical
                ToolButton {
                    id: btnZoomHorizontal
                    iconSource: "qrc:/resources/images/pan_horizontal.png"
                    enabled: true
                    tooltip: "Pan / Zoom Horizontal"
                    checked: false
                    checkable: true
                    exclusiveGroup: egTools
                    onClicked: {
                        graphScreen.toolMode = "zoomHorizontal";
                    }
                } // btnZoomHorizontal
                ToolButton {
                    id: btnBadData
                    iconSource: "qrc:/resources/images/invalid_data.png"
                    tooltip: "Mark as Invalid"
                    checked: false
                    checkable: true
                    exclusiveGroup: egTools
                    onClicked: {
                        graphScreen.toolMode = "invalidData";
                    }
                } // btnBadData
                Item { Layout.preferredWidth: 20 }
                ToolButton {
                    id: btnToggleLegend
                    iconSource: "qrc:/resources/images/legend.png"
                    tooltip: "Toggle Legend"
                    checked: false
                    checkable: true
                    onClicked: {
                        var graphName = tvGraphs.getTab(tvGraphs.currentIndex).title;
                        graphScreen.toggleLegend(graphName, checked);
                    }
                } // btnToggleLegend
                ToolButton {
                    id: btnToggleInvalids
                    iconSource: "qrc:/resources/images/eye.png"
                    tooltip: "Toggle Invalid Data Points"
                    checked: false
                    checkable: true
                    onClicked: { graphScreen.toggleInvalids(checked) }
                } // btnToggleInvalids
                ToolButton {
                    id: btnToggleTooltips
                    iconSource: "qrc:/resources/images/tooltip.png"
                    tooltip: "Toggle Tooltips"
                    checked: false
                    checkable: true
                    onClicked: { graphScreen.toggleTooltips(checked) }
                } // btnToggleInvalids
                ToolButton {
                    id: btnToggleUpDown
                    iconSource: "qrc:/resources/images/" + graphScreen.upDownCasts + ".png"
                    tooltip: "Toggle Downcast / Upcast"
                    checked: false
                    checkable: false
                    onClicked: { graphScreen.toggleUpDownCast(iconSource) }
                } // btnToggleUpDown

                Item { Layout.preferredWidth: 20 }
                ToolButton {
                    id: btnUndo
                    iconSource: "qrc:/resources/images/undo.png"
                    tooltip: "Undo Last Action"
                    checked: false
                    checkable: false
                    onClicked: {

                    }
                } // btnUndo
                ToolButton {
                    id: btnAdjustColor
                    iconSource: "qrc:/resources/images/color.png"
                    tooltip: "Adjust Graph Colors"
                    checked: false
                    checkable: false
                    onClicked: { //timeSeries.showInvalids = checked
                    }
                } // btnAdjustColor
                ToolButton {
                    id: btnSaveImage
                    iconSource: "qrc:/resources/images/save.png"
                    tooltip: "Save Graphs as Images"
                    checked: false
                    checkable: false
                    onClicked: { // timeSeries.showInvalids = checked
                    }
                } // btnSaveImage
            } // rlTools
            TabView {
                id: tvGraphs
                objectName: "graphTabView"
                Layout.fillWidth: true
                Layout.fillHeight: true
//                style: TabViewStyle {
//                    frameOverlap: 1
//                    tab: Rectangle {
//                        color: styleData.selected ? "steelblue" :"lightsteelblue"
//                        border.color:  "steelblue"
//                        implicitWidth: Math.max(text.width + 4, 80)
//                        implicitHeight: 20
//                        radius: 2
////                        RowLayout {
////                            spacing: 5
//                            Text {
//                                id: text
//                                anchors.centerIn: parent
//                                text: styleData.title
//                                color: styleData.selected ? "white" : "black"
//                            }
//                            Button {
//                                id: btnDelete
//                                anchors.right: parent.right
//                                anchors.rightMargin: 5
//                                text: qsTr("x")
//                                width: 20
////                                Layout.preferredWidth: 20
//                            }
////                        }
//                    }
//                    frame: Rectangle { color: "steelblue" }
//                }
            } // Tab Graphs
        } // clMapPanel
    } // rlCastsVariables

//    } // svTimeSeries
}
