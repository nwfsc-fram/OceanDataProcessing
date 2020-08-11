import os
import logging
import re
import gc

import pandas as pd

from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot, QObject, QVariant, QThread, Qt

from py.utilities.FramListModel import FramListModel
from py.MplGraph import MplGraph
from  py.qaqc import butterworth_filter, set_downcast, set_vertical_velocity, low_pass_filter_pressure_velocity, \
    low_pass_filter_pressure, correct_thermal_mass, correct_loop_edit
from py.seawater import sw_dens, sw_pden

# Variables to show for possible plotting
CTD_VARIABLES = ["Depth (m)",
             "Temperature (degC)",
             "Temperature (degC) (Secondary)",
             "Conductivity (S_per_m)",
             "Conductivity (S_per_m) (Secondary)",
             "Salinity (psu)",
             "Salinity (psu) (Secondary)",
             "Density ()",
             "Oxygen (ml_per_l)",
             "Oxygen (ml_per_l) (Secondary)",
             "Sound Velocity (Chen Millero)"]
UCTD_VARIABLES = ["Temperature (degC)",
                  "Pressure (decibar)",
                  "Depth (m)",
                  "Conductivity (S_per_m)"
                  "Salinity (psu)",
                  "Sound Velocity (m_per_s) (cm)",
                  "Sound Velocity (m_per_s) (d)",
                  "Sound Velocity (m_per_s) (w)"]
SBE39_VARIABLES = ["Temperature_degC",
                   "Depth_m"]


# Standard Graphs to plot for a given cast
CTD_STANDARD_GRAPHS = {
                   "Graph 1": {"x": ["Temperature (degC)", "Temperature (degC) (Secondary)"], "y": "Depth (m)"},
                   "Graph 2": {"x": ["Temperature (degC)"], "y": "Depth (m)"},
                   "Graph 3": {"x": ["Temperature (degC) (Secondary)"], "y": "Depth (m)",
                                "title": "Temperature (degC) (Secondary) v. Depth (m)"},
                   "Graph 4": {"x": ["Conductivity (S_per_m)", "Conductivity (S_per_m) (Secondary)"], "y": "Depth (m)"},
                   "Graph 5": {"x": ["Conductivity (S_per_m)"], "y": "Depth (m)"},
                   "Graph 6": {"x": ["Conductivity (S_per_m) (Secondary)"], "y": "Depth (m)",
                                "title": "Conductivity (S_per_m) (Secondary) v. Depth (m)"},
                   "Graph 7": {"x": ["Salinity (psu)", "Salinity (psu) (Secondary)"], "y": "Depth (m)"},
                   "Graph 8": {"x": ["Oxygen (ml_per_l)", "Oxygen (ml_per_l) (Secondary)"], "y": "Depth (m)"},
                   "Graph 9": {"x": ["Oxygen (ml_per_l)"], "y": "Depth (m)"},
                   "Graph 10": {"x": ["Oxygen (ml_per_l) (Secondary)"], "y": "Depth (m)",
                                "title": "Oxygen (ml_per_l) (Secondary) v. Depth (m)"},
                   "Graph 11": {"x": ["Seawater Density (kg/m3)"], "y": "Depth (m)"},
                   "Graph 12": {"x": ["Sigma Theta", "Sigma Theta (Secondary)"], "y": "Depth (m)"},
                   "Graph 13": {"x": ["Sigma Theta"], "y": "Depth (m)"},
                   "Graph 14": {"x": ["Sigma Theta (Secondary)"], "y": "Depth (m)",
                                "title": "Sigma Theta (Secondary) v. Depth (m)"},
}

UCTD_STANDARD_GRAPHS = {
    "Graph 1": {"x": ["Temperature (degC)"], "y": "Depth (m)"},
    "Graph 2": {"x": ["Conductivity (S_per_m)"], "y": "Depth (m)"},
    "Graph 3": {"x": ["Salinity (psu)"], "y": "Depth (m)"},
    "Graph 4": {"x": ["Seawater Density (kg/m3)"], "y": "Depth (m)"},
    "Graph 5": {"x": ["Sigma Theta"], "y": "Depth (m)"},
    "Graph 6": {"x": ["dPdt"], "y": "Depth (m)"}
}


class FilesWorker(QObject):

    loadStatus = pyqtSignal(bool, str)
    rowFound = pyqtSignal(dict)

    def __init__(self, app=None, **kwargs):
        super().__init__(**kwargs)
        self._app = app
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):

        try:
            self.is_running = True

            items = list()
            converted_path = self._app.settings.convertedPath
            qaqc_path = self._app.settings.qaqcPath

            csv_files = [os.path.basename(f) for f in os.listdir(converted_path)
                         if re.search(r'.*\.csv$', f)]
            pickle_files = [os.path.basename(f) for f in os.listdir(qaqc_path)
                         if re.search(r'.*\.pickle$', f)]
            pickle_name_only = [os.path.splitext(f)[0] for f in pickle_files]

            logging.info(f"\tGraphScreen converted_path csv files = {csv_files}")
            logging.info(f"\tGraphScreen qaqc_path pickle files = {pickle_files}")
            for csv in csv_files:
                if not self.is_running:
                    break
                root, ext = os.path.splitext(csv)
                if root not in pickle_name_only:

                    logging.info(f"creating pickle file: {csv} > {root}")
                    df = pd.read_csv(os.path.join(converted_path, csv))

                    if not os.path.exists(qaqc_path):
                        os.makedirs(qaqc_path)

                    # Add the invalid columns into the dataframe
                    # columns = {f"{x} invalid": False for x in VARIABLES}
                    # invalid_cols = [f"{x} invalid" for x in list(df.columns.values)]
                    # columns = {f"{x} invalid": False for x in list(df.columns.values)}

                    extra_columns = ["Temperature (degC)", "Conductivity (S_per_m)", "Pressure (decibar)", "dPdt",
                                     "Seawater Density (kg/m3)", "Sigma Theta", "Sigma Theta (Secondary)"]
                    columns = {f"{x} invalid": False for x in list(df.columns.values) + extra_columns}
                    df = df.assign(**columns)

                    # Calculate the descent and add to the dataframe
                    df = set_downcast(df=df)

                    # Compute the vertical velocity (dBar/s) from central difference
                    df = set_vertical_velocity(df=df)


                    if self._app.settings.instrument == "CTD":

                        # Low Pass Filter the Pressure
                        sampling_frequency = 24
                        cutoff_per = 4 * (1 / sampling_frequency)  # Seabird Data Processing manual, p. 100
                        df = low_pass_filter_pressure(df=df, cutoff_per=cutoff_per)

                        # Perform the thermomass cell correction
                        cols = list(df.columns.values)
                        if "Pressure (decibar)" in cols and \
                            "Temperature (degC)" in cols and \
                            "Conductivity (S_per_m)" in cols:

                            P = df['Pressure (decibar)']
                            T = df['Temperature (degC)']
                            C = df['Conductivity (S_per_m)']
                            alpha = 0.03
                            tau = 7.0
                            df.loc[:, "Conductivity (S_per_m)"] = correct_thermal_mass(C=C, T=T, P=P, alpha=alpha, tau=tau)

                        # Perform loop edit correction
                        window_time = 300  # seconds
                        df = correct_loop_edit(df=df, window_time=window_time, sampling_frequency=sampling_frequency)

                        if "Salinity (psu)" in cols and \
                            "Temperature (degC)" in cols and \
                            "Pressure (decibar)" in cols:

                            # Calculate Sea Water Density
                            df.loc[:, "Seawater Density (kg/m3)"] = sw_dens(
                                S=df["Salinity (psu)"],
                                T=df["Temperature (degC)"],
                                P=df["Pressure (decibar)"])

                            df.loc[:, "Seawater Density (kg/m3) invalid"] = False

                            # Calculate Sigma_Theta
                            pr = 0  # Surface Pressure Reference
                            df.loc[:, "Sigma Theta"] = sw_pden(S=df["Salinity (psu)"],
                                                               T=df["Temperature (degC)"],
                                                               P=df["Pressure (decibar)"],
                                                               PR=pr) - 1000

                            df.loc[:, "Sigma Theta invalid"] = False


                        if "Salinity (psu) (Secondary)" in cols and \
                            "Temperature (degC) (Secondary)" in cols and \
                            "Pressure (decibar)" in cols:

                            # Calculate Sea Water Density (Secondary)
                            df.loc[:, "Seawater Density (kg/m3) (Secondary)"] = sw_dens(S=df["Salinity (psu) (Secondary)"],
                                                                        T=df["Temperature (degC) (Secondary)"],
                                                                        P=df["Pressure (decibar)"])
                            df.loc[:, "Seawater Density (kg/m3) (Secondary) invalid"] = False

                            # Calculate Sigma_Theta (Secondary
                            pr = 0  # Surface Pressure Reference
                            df.loc[:, "Sigma Theta (Secondary)"] = sw_pden(S=df["Salinity (psu) (Secondary)"],
                                                               T=df["Temperature (degC) (Secondary)"],
                                                               P=df["Pressure (decibar)"],
                                                               PR=pr) - 1000
                            df.loc[:, "Sigma Theta (Secondary) invalid"] = False

                        if "Pressure (decibar)" in cols:
                            mask = (df["Pressure (decibar)"] <= 2)
                            df.loc[mask, [f"{x} invalid" for x in extra_columns]] = True

                    elif self._app.settings.instrument == "UCTD":

                        # low pass filter the pressure and vertical velocity
                        df = low_pass_filter_pressure_velocity(df=df)

                        # TODO Todd Hay - Add in remaining UCTD auto-QA/QC processing steps

                    # Drop unnecessary columns
                    cols = list(df.columns.values)
                    drop_cols = []
                    for col in ["time", "dp", "dt", "dpdt", "dpdt_f", "is_descent", "Descent Rate (dz_per_dt)",
                                "dPdt_mean"]:
                        if col in cols:
                            drop_cols.append(col)
                    if len(drop_cols) > 0:
                        df.drop(drop_cols, axis=1, inplace=True)

                    # Save the pickle file on disk
                    logging.info(f"saving the pickle to disk: {root}.pickle")
                    df.to_pickle(os.path.join(qaqc_path, f"{root}.pickle"))

                item = {"cast": root, "pickleExists": True}
                self.rowFound.emit(item)

            status = True
            message = "Successful found QA/QC files"

        except Exception as ex:

            status = False
            message = f"Populating files error: {ex}"
            logging.info(message)


        self.loadStatus.emit(status, message)


class FilesModel(FramListModel):

    def __init__(self, app=None, db=None):
        super().__init__()
        self._app = app
        self._db = db
        self.add_role_name(name="cast")
        self.add_role_name(name="pickleExists")

        self._thread = QThread()
        self._worker = FilesWorker(app=self._app)
        self._worker.moveToThread(self._thread)
        self._worker.loadStatus.connect(self._load_status_received)
        self._worker.rowFound.connect(self._row_found)
        self._thread.started.connect(self._worker.run)

        # if self._app.settings.qaqcPath:
        #     self.populate()

    def stop(self):
        """
        Method to stop the worker
        :return:
        """
        self._worker.stop()
        self.clear()

    @pyqtSlot()
    def populate(self):
        """
        Method to populate the FilesModel by querying the folder to determine which hex and csv
        files already exist for the given survey and vessel that are defined in the
        self._app.settings class instance
        :return:
        """
        logging.info(f"\tGraphScreen - populating the GraphScreen.FilesModel, qaqcPath = {self._app.settings.qaqcPath}")
        if self._thread.isRunning():
            self._worker.stop()
            # self._thread.quit()
        self.clear()
        self._thread.start()

    def _row_found(self, item):
        """
        Method to catch a new row that was found via the worker and add it to this model
        :param item:
        :return:
        """
        if not isinstance(item, dict):
            return

        self.appendItem(item=item)

    def _load_status_received(self, status, message):
        """
        Method to catch the signal from the thread for loading the files.  This returns two values:
        - status which is true / false if it was successful or not, and a message
        :param status:
        :param message:
        :return:
        """
        # logging.info(f"thread finished, status={status}, message={message}")
        self._thread.quit()


class VariablesModel(FramListModel):

    def __init__(self, app=None, db=None):
        super().__init__()
        self._app = app
        self._db = db
        self.add_role_name(name="variable")

        self.populate()

    def populate(self, instrument="CTD"):
        """
        Method to populate the model
        :return:
        """
        self.clear()

        variable_list = {
            "CTD": CTD_VARIABLES,
            "UCTD": UCTD_VARIABLES,
            "SBE39": SBE39_VARIABLES
        }

        if instrument in variable_list:
            for v in variable_list[instrument]:
                self.appendItem({"variable": v})


class LoadGraphDataWorker(QObject):

    dataLoadedStatus = pyqtSignal(bool, str, QVariant)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.source_file = None
        self.is_running = False

    def stop(self):
        self.is_running = False

    def run(self):

        try:
            self.is_running = True

            df = None
            status = False

            if not os.path.exists(self.source_file):

                message = f"Pickle file not found: {self.source_file}, not plotting"
                logging.error(message)

            else:
                df = pd.read_pickle(path=self.source_file)
                status = True
                message = f"Successfully loaded the dataframe: {self.source_file}"

        except Exception as ex:

            message = f"Graph plotting error: {ex}"
            logging.error(message)

        self.dataLoadedStatus.emit(status, message, df)


class SavePickleWorker(QObject):

    pickleSavedStatus = pyqtSignal(bool, str)

    def __init__(self, df=None, pickle_file=None, **kwargs):
        super().__init__(**kwargs)
        self._df = df
        self._pickle_file = pickle_file
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):

        try:
            self.is_running = True

            if not os.path.exists(self._pickle_file):
                logging.error(f"Pickle file path not found: {self._pickle_file}")
                return

            self._df.to_pickle(path=self._pickle_file)

            # Force another save, as the is_running was set to false during the time that the
            # to_pickle operation was started
            if not self.is_running:
                logging.info(f"pickling again...")
                self.is_running = True
                self._df.to_pickle(path=self._pickle_file)

            status = True
            message = "Successfully saved pickle file"

        except Exception as ex:

            status = False
            message = f"Saving pickle error: {ex}"

        self.pickleSavedStatus.emit(status, message)


class GraphScreen(QObject):
    """
    Class for the GraphScreen
    """
    filesModelChanged = pyqtSignal()
    variablesModelChanged = pyqtSignal()
    clearGraphs = pyqtSignal()
    standardGraphsChanged = pyqtSignal()
    graphsChanged = pyqtSignal()
    isDFLoadedChanged = pyqtSignal()
    allGraphsDeleted = pyqtSignal()

    toolModeChanged = pyqtSignal()
    showInvalidsChanged = pyqtSignal()
    upDownCastsChanged = pyqtSignal()

    def __init__(self, app=None):
        super().__init__()

        # self._logger = logging.getLogger(__name__)
        self._app = app
        self._graphs = dict()
        self._cast = None
        self._df = None
        self._source_file = None
        self._standard_graphs = CTD_STANDARD_GRAPHS

        # Thread + Worker for loading the pandas data frame
        self._loader_thread = QThread()
        self._loader_worker = LoadGraphDataWorker()
        self._loader_worker.moveToThread(self._loader_thread)
        self._loader_worker.dataLoadedStatus.connect(self._cast_loaded)
        self._loader_thread.started.connect(self._loader_worker.run)
        self._is_df_loaded = False

        # Thread + Worker for auto-saving data frame to a pickle file
        self._saver_thread = QThread()
        self._saver_worker = None

        # Models for populating the Casts and Variables TableViews
        self._files_model = FilesModel(app=self._app)
        self._variables_model = VariablesModel(app=self._app)

        # Tool Modes
        self._tool_mode = "pan"
        self._show_invalids = False
        self._show_tooltips = False
        self._up_down_casts = "down"

    @pyqtProperty(QVariant, notify=graphsChanged)
    def graphs(self):
        """
        Method to return the self._graphs
        :return:
        """
        return self._graphs

    @pyqtSlot(int, str, name="keyPressed")
    def key_pressed(self, graph, action):
        """
        Method called when a key is pressed for zooming in or out on one of the charts.  This is called by the
        MainWindow.qml as that is where key presses are captured
        :param action:
        :return:
        """
        if f"Graph {graph+1}" in self._graphs:
            self._graphs[f"Graph {graph+1}"].key_zoom(action=action)

    @pyqtProperty(QVariant, notify=standardGraphsChanged)
    def standardGraphs(self):
        """
        Method to return the self._standard_graphs variable which defines what are the standard
        graphs to plot to the GraphScreen
        :return:
        """
        if self._app.settings.instrument == "CTD":
            self._standard_graphs = CTD_STANDARD_GRAPHS
        elif self._app.settings.instrument == "UCTD":
            self._standard_graphs = UCTD_STANDARD_GRAPHS
        return self._standard_graphs

    @pyqtProperty(bool, notify=isDFLoadedChanged)
    def isDFLoaded(self):
        """
        Method to return the self._is_df_loaded variable
        :return:
        """
        return self._is_df_loaded

    @isDFLoaded.setter
    def isDFLoaded(self, value):
        """
        Method to set the self._is_df_loaded variable
        :param value:
        :return:
        """
        if not isinstance(value, bool):
            return

        self._is_df_loaded = value
        self.isDFLoadedChanged.emit()

    @pyqtProperty(str, notify=toolModeChanged)
    def toolMode(self):
        """
        Method to return the self._tool_mode
        :return:
        """
        return self._tool_mode

    @toolMode.setter
    def toolMode(self, value):
        """
        Method to set the self._tool_mode
        :param value:
        :return:
        """
        self._tool_mode = value
        for graph in self._graphs:
            self._graphs[graph]._tool_mode = value

        self.toolModeChanged.emit()

    @pyqtProperty(FramListModel, notify=filesModelChanged)
    def filesModel(self):
        """
        Method to return the self._files_model for use in the ConvertScreen.qml as the model for
        the primary TableView
        :return:
        """
        return self._files_model

    @pyqtProperty(FramListModel, notify=variablesModelChanged)
    def variablesModel(self):
        """
        Method to return the variables model to the GraphScreen.qml
        :return:
        """
        return self._variables_model

    def stop_threads(self):
        """
        Method to stop the filesModel and convert worker background threads
        :return:
        """
        # Stop the FileWorker thread
        if self.filesModel._worker:
            self.filesModel._worker.stop()

        if self._saver_worker:
            self._saver_worker.stop()

        if self._loader_worker:
            self._loader_worker.stop()

    @pyqtSlot(str, str, str, QVariant, QVariant, name="plotGraph")
    def plot_graph(self, graph_name, mpl_object_name, x, y, title=None):
        """
        Method to plot a graph line
        :param graph_name:
        :param mpl_object_name:
        :param x:
        :param y:
        :return:
        """
        try:

            # logging.info(f"Plot variables: {graph_name}, {mpl_object_name}, {x}, {y}")

            if self._is_df_loaded:

                # logging.info(f"############## Plotting {graph_name} ###################")

                # Create the new Graph if it doesn't already exist
                if graph_name not in self._graphs:
                    # logging.info(f"creating a new graph: {graph_name}")
                    qml_item = self._app.engine.rootObjects()[0].findChild(QObject, mpl_object_name)
                    self._graphs[graph_name] = MplGraph(qml_item=qml_item, graph_name=graph_name, df=self._df,
                                                        tool_mode=self._tool_mode, show_invalids=self._show_invalids,
                                                        show_tooltips=self._show_tooltips)
                    self._graphs[graph_name].valids_invalids_changed.connect(self.update_dataframe)
                    self._graphs[graph_name].cursor_moved.connect(self.update_status_bar)

                # Plot the data
                self._graphs[graph_name].plot_graph(x=x, y=y, title=title)

            else:
                logging.info(f"df is not loaded, so nothing to do")

        except Exception as ex:

            logging.error(f"Error plotting graph: {ex}")

    @pyqtSlot(name="plotStandardGraphs")
    def plot_standard_graphs(self): #, objects):
        """
        Method called by the GraphScreen.qml screen to plot the standard suite of graphs as defined
        by self._standard_graphs (the source is at the top of this file in a global variable called STANDARD_GRAPHS)
        :param objects: List - contains the name of all of the QML mplGraph items that were just created
        :return: None
        """
        # if isinstance(objects, QJSValue):
        #     objects = objects.toVariant()

        # Delete the existing plot lines and set the graphs dataframe to the current dataframe
        for g in self._graphs:
            del self._graphs[g].axis.lines[:]
            self._graphs[g].qml_item.draw_idle()
            self._graphs[g].df = self._df

        # for mpl_object_name in objects:
        for graph_name in self._standard_graphs:
            # graph_name = mpl_object_name.replace("mplFigure", "Graph ")
            mpl_object_name = graph_name.replace("Graph ", "mplFigure")
            # if graph_name in self._standard_graphs:
            if "y" in self._standard_graphs[graph_name]:
                y = self._standard_graphs[graph_name]["y"]
                for x in self._standard_graphs[graph_name]["x"]:
                    title = None
                    if "title" in self._standard_graphs[graph_name]:
                        title = self._standard_graphs[graph_name]["title"]
                    self.plot_graph(graph_name=graph_name, mpl_object_name=mpl_object_name, x=x, y=y, title=title)

        # Set the focus on the first graph, which is what is initially shown, so that it can accept key events
        if "Graph 1" in self._graphs.keys():
            self._graphs['Graph 1'].canvas.setFocusPolicy(Qt.ClickFocus)
            self._graphs['Graph 1'].canvas.setFocus()

    @pyqtSlot(bool, name="deleteAllGraphs")
    def delete_all_graphs(self, plot_standards):
        """
        Method called to delete all of the existing graphs
        """
        try:

            for g in list(self._graphs):
                self.delete_graph(graph_name=g)

            if plot_standards:
                self.allGraphsDeleted.emit()

        except Exception as ex:

            logging.error(f"Error deleting all of the graphs: {ex}")

    @pyqtSlot(str, name="deleteGraph")
    def delete_graph(self, graph_name):
        """
        Method to delete the graph with the name of graph_name
        :param graph_name:
        :return:
        """
        try:

            if graph_name in self._graphs:

                # Delete the graph axis - Not really sure that I need to do this
                ax = self._graphs[graph_name].axis
                self._graphs[graph_name].figure.delaxes(ax)

                # Delete the graph
                self._graphs.pop(graph_name, None)
                logging.info(f"{graph_name} successfully deleted")

            gc.collect()

        except Exception as ex:

            logging.error(f"Failed to delete {graph_name}: {ex}")

    def _check_cast(self, cast):
        """
        Method to determine if the cast is different or not then the currently selected cast
        :param cast: str - representing the cast
        :return:
        """
        if cast != self._cast:

            # Save the current dataframe back down as a pickle file before clearing it out, just in case
            # pending valid / invalid updates have not been saved yet
            if self._cast:
                self.save_pickle_file()

            # Clear out the dataframe and the graphs
            del self._df
            self._df = None

            # for g in self._graphs:
            #     ax = self._graphs[g].axis
            #     self._graphs[g].figure.delaxes(ax)
            #     self._graphs[g].figure.close()
            #     for i, line in enumerate(g.axis.lines):
            #         g.axis.lines.pop(i).remove()
            # self._graphs.clear()

            # Set the self._cast to the newly provided cast
            self._cast = cast

    @pyqtSlot(str, name="loadCast")
    def load_cast(self, cast):
        """
        Method called to load the dataframe that is used for plotting all of the graphs for the
        current cast
        :param cast: str - representing the selected cast
        :return:
        """
        if not isinstance(cast, str) or cast == "":
            logging.error(f"Cannot load dataframe due to invalid cast: {cast}")
            return

        try:

            # Check to see if the cast is the same as the current cast or not
            self._check_cast(cast=cast)

            # Set the dataframe loaded flag to false
            self.isDFLoaded = False

            # Create the source_file path to the dataframe pickle file (this should have
            # been created during the convert process)
            if not os.path.exists(self._app.settings.qaqcPath):
                os.makedirs(self._app.settings.qaqcPath)
            self._source_file = os.path.join(self._app.settings.qaqcPath, f"{cast}.pickle")

            # Load the data frame via a background thread
            self._loader_worker.source_file = self._source_file
            self._loader_thread.start()

        except Exception as ex:

            logging.error(f"Failed loading the dataframe: {ex}")

    def _cast_loaded(self, status, message, df):
        """
        Method to catch the dataframe loaded for the graph and to plot it
        :param status: bool - True / False - was it successful or not
        :param message: str - message of what happened during the dataframe loading
        :param df: dataframe - dataframe from which to load data
        :return:
        """
        if self._loader_thread:
            self._loader_thread.quit()

        # logging.info(f"data loaded status: {status} > {message}")

        if status:

            self._df = df
            self.isDFLoaded = True

            # logging.info(f"df columns: {self._df.columns.values}")

    @pyqtSlot(str, bool, name="toggleLegend")
    def toggle_legend(self, graph_name, status):
        """
        Method to toggle the matplotlib legend for the given graph_name
        :param status:
        :return:
        """
        if graph_name in self._graphs and isinstance(status, bool):
            self._graphs[graph_name].toggle_legend(status)

    @pyqtSlot(bool, name="toggleTooltips")
    def toggle_tooltips(self, status):
        """
        Method to turn the visibility of the x/y data tooltips on or off
        :param status:
        :return:
        """
        if not isinstance(status, bool):
            logging.error(f"Tooltip status is not a boolean: {status}")
            return

        for g in self._graphs:
            self._graphs[g].toggle_tooltips(visibility=status)
        self._show_tooltips = status

    @pyqtSlot(bool, name="toggleInvalids")
    def toggle_invalids(self, status):
        """
        Method to toggle the visibility of the invalid points
        :param status:
        :return:
        """
        if not isinstance(status, bool):
            return

        for g in self._graphs:
            self._graphs[g].toggle_invalids(visibility=status)

        self._show_invalids = status

    @pyqtSlot(str, name="toggleUpDownCast")
    def toggle_up_down_cast(self, icon):
        """
        Method to toggle the viewing of the downcast, upcast, or both
        :param icon:
        :return:
        """
        mapping = {"down": "updown", "updown": "up", "up": "down"}
        value = icon.split("/")[-1][:-4]
        new_value = mapping[value]
        self._up_down_casts = new_value
        self.upDownCastsChanged.emit()

        for g in self._graphs:
            self._graphs[g].toggle_upcast_downcast(value=new_value)

    @pyqtProperty(str, notify=upDownCastsChanged)
    def upDownCasts(self):
        """
        Method to return the self._show_up_down_casts
        :return:
        """
        return self._up_down_casts

    def update_dataframe(self,  x, y, new_valid_xy_values, new_invalid_xy_values):
        """
        Method to update the dataframe.  This method is call from one of the instantiated
        MplGraph objects after the user has captured new valid or invalid data points
        :param x: x variable name
        :param y: y variable name
        :param valid_xy_data: list of new x/y valid data
        :param invalid_xy_data: list of new x/y inavlid data
        :return:
        """
        logging.info(f"Updating, x = {x}, y = {y}")
        logging.info(f"\n\tnew valids: {new_valid_xy_values}\n\tnew invalids: {new_invalid_xy_values}")

        # All of the x's have downcast or upcast in their names, but the dataframe does not, so remove those texts
        x_df = x.replace(" downcast", "").replace(" upcast", "")
        x_invalid = f"{x_df} invalid" if "invalid" not in x else x
        y_invalid = f"{y} invalid" if "invalid" not in y else y

        logging.info(f"\tx_df={x_df}, x_invalid={x_invalid}, y_invalid={y_invalid}")

        # Update the new valid points
        if len(new_valid_xy_values) > 0:
            df_valids_idx = pd.DataFrame(data=new_valid_xy_values, columns=[x_df, y])
            df_idx = pd.merge(self._df.reset_index(), df_valids_idx, how="inner").set_index("index")
            self._df.loc[df_idx.index.values, [x_invalid, y_invalid]] = False

        # Update the new invalid points
        if len(new_invalid_xy_values) > 0:
            df_invalids_idx = pd.DataFrame(data=new_invalid_xy_values, columns=[x_df, y])
            df_idx = pd.merge(self._df.reset_index(), df_invalids_idx, how="inner").set_index("index")
            self._df.loc[df_idx.index.values, [x_invalid, y_invalid]] = True

        # Update the dataframes for each of the children graphs
        for g in self._graphs:
            self._graphs[g].df = self._df

        # Save the updated dataframe back down as a pickle file
        self.save_pickle_file()

        # Create the dataframe mask - This would return the valid data points for the given x/y variables
        mask = (~self._df[f"{x_df} invalid"]) & (~self._df[f"{y} invalid"])
        valid_mask = (~self._df[f"{x_df} invalid"])

        # Redraw the graphs if their x/y variables match those that were updated
        for graph in self._graphs:

            logging.info(f"\tUpdating {graph} > {x}, {y}")

            upcast_vis = self._graphs[graph]._upcast_visibility
            downcast_vis = self._graphs[graph]._downcast_visibility

            logging.info(f"\tupcast vis={upcast_vis}, downcast vis={downcast_vis}")

            # Mask for the is_downcast column to determine if we are plotting upcast, downcast, or both
            mask_up = (self._df["is_downcast"] == 0)
            mask_down = (self._df["is_downcast"] == 1)

            # if upcast_vis and downcast_vis:
            #     masks = [mask_up, mask_down]
            # elif upcast_vis:
            #     masks = [mask_up]
            # elif downcast_vis:
            #     masks = [mask_down]
            # df_cast = self._df.loc[mask]

            # Mask each line for the invalids
            # lines = [l.get_label() for l in self._graphs[graph].axis.lines]
            # logging.info(f"lines = {lines}")

            valid_lines = [l for l in self._graphs[graph].axis.lines if l.get_label() == x or l.get_label() == y]
            logging.info(f"valid lines = {[l.get_label() for l in valid_lines]}")
            for valid_line in valid_lines:

                if "downcast" in valid_line.get_label():
                    mask = mask_down
                elif "upcast" in valid_line.get_label():
                    mask = mask_up
                df_cast = self._df.loc[mask]

                # Reset data for the valid line
                df_valid = df_cast.loc[valid_mask]
                valid_line.set_data(df_valid[x_df], df_valid[y])

                # Reset the data for the invalid line
                invalid_lines = [l for l in self._graphs[graph].axis.lines if l.get_label() == f"{x} invalid"]
                if len(invalid_lines) == 1:
                    df_invalid = df_cast.loc[~valid_mask]
                    invalid_line = invalid_lines[0]
                    invalid_line.set_data(df_invalid[x_df], df_invalid[y])

            self._graphs[graph].qml_item.draw_idle()

    def update_status_bar(self, x, y):
        """
        Method to catch graph cursor movements for updating the status bar with the current graph x / y values
        :param x:
        :param y:
        :return:
        """
        if isinstance(x, float) and isinstance(y, float):
            self._app.settings.statusBarMessage = f"x: {x},   y: {y}"

    @pyqtSlot(name="savePickleFile")
    def save_pickle_file(self):
        """
        Method to save the data frame to a pickle file.  This is called when the data frame is
        changed, such as when selecting points as being invalid or valid.
        :return:
        """
        try:

            # TODO Todd Hay - Need to check if the thread is already running and if so, cancel and then run it
            if self._saver_thread.isRunning():

                # self._saver_thread.quit()
                self._saver_worker.stop()

            else:

                self._saver_worker = SavePickleWorker(df=self._df, pickle_file=self._source_file)
                self._saver_worker.moveToThread(self._saver_thread)
                self._saver_worker.pickleSavedStatus.connect(self._pickle_saved)
                self._saver_thread.started.connect(self._saver_worker.run)
                self._saver_thread.start()

        except Exception as ex:

            logging.error(f"Error plotting graph: {ex}")

    def _pickle_saved(self, status, message):
        """
        Method to catch the result coming from the saver_worker thread
        :param status:
        :param message:
        :return:
        """
        if self._saver_thread:
            self._saver_thread.quit()
        logging.info(f"pickle saved: {status}, {message}")


