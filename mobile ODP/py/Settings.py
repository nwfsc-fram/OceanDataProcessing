__author__ = 'Todd.Hay'
# -----------------------------------------------------------------------------
# Name:        Settings.py
# Purpose:     Global settings
#
# Author:      Todd Hay <todd.hay@noaa.gov>
#
# Created:     Dec 12, 2016
# License:     MIT
# ------------------------------------------------------------------------------
PROD = False


import logging
import unittest
import os
import re
import glob
import shutil
import configparser as cp

from PyQt5.QtCore import pyqtProperty, QObject, pyqtSignal, pyqtSlot, \
    QVariant, QThread
from PyQt5.QtQml import QJSValue

from py.utilities.FramListModel import FramListModel


class Worker(QObject):

    loadStatus = pyqtSignal(bool, str, list)

    def __init__(self, app=None, survey_path=None, **kwargs):
        super().__init__(**kwargs)
        self._app = app
        self._survey_path = survey_path
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):

        try:
            self.is_running = True
            items = list()
            try:

                items = [{"text": os.path.basename(s)} for s in
                         os.listdir(self._survey_path) if
                         s[:4].isdigit() and s[4] == " "
                         and os.path.isdir(os.path.join(self._survey_path, s))]
                items.insert(0, {"text": "Select Survey"})

            except Exception as ex:

                logging.info(f"Error retrieving the survey names: {ex}")

            status = True
            message = "Successful loading of model files"

        except Exception as ex:

            status = False
            message = f"Populating files error: {ex}"

        self.loadStatus.emit(status, message, items)


class VesselModel(FramListModel):

    def __init__(self, app=None):
        super().__init__()
        self._app = app
        self.add_role_name(name="text")

        self.populate()

    @pyqtSlot(str)
    def populate(self, survey=None):
        """
        Method to initially populate the model
        :return:
        """
        self.clear()

        self.appendItem({"text": "Select Vessel"})

        if survey and survey != "Select Survey":

            vessels = survey.split(" ")[-1]
            if "_" in vessels:
                vessels = vessels.split("_")
            else:
                vessels = {vessels}

            for v in vessels:
                self.appendItem({"text": v})


class SurveyModel(FramListModel):

    surveyModelChanged = pyqtSignal()

    def __init__(self, app=None, survey_path=None):
        super().__init__()
        self._app = app
        self._survey_path = survey_path

        self.add_role_name(name="text")

        self._thread = QThread()
        self._worker = Worker(app=self._app, survey_path=self._survey_path)
        self._worker.moveToThread(self._thread)
        self._worker.loadStatus.connect(self._load_status_received)
        self._thread.started.connect(self._worker.run)

        self.populate()

    def populate(self):
        """
        Method to initially populate the model
        :return:
        """
        self.clear()
        self._thread.start()

    def _load_status_received(self, status, message, items):
        """
        Method to catch the signal from the thread for loading the files.  This returns two values:
        - status which is true / false if it was successful or not, and a message
        :param status:
        :param message:
        :param items:
        :return:
        """
        self._thread.quit()
        for item in items:
            self.appendItem(item)

        self.surveyModelChanged.emit()


class Settings(QObject):
    """
    Handles Trawl Backdeck settings and related database interactions
    """
    isDeployedChanged = pyqtSignal()
    dataPathChanged = pyqtSignal()

    surveyChanged = pyqtSignal()
    vesselChanged = pyqtSignal()
    instrumentChanged = pyqtSignal()

    surveyModelChanged = pyqtSignal()
    vesselModelChanged = pyqtSignal()
    locationsPathChanged = pyqtSignal()
    rawPathChanged = pyqtSignal()
    convertedPathChanged = pyqtSignal()
    qaqcPathChanged = pyqtSignal()
    binnedPathChanged = pyqtSignal()
    graphTabChanged = pyqtSignal()

    # pingStatusReceived = pyqtSignal(str, bool, arguments=['message', 'success'])

    isProductionChanged = pyqtSignal()
    statusBarMessageChanged = pyqtSignal()
    sourceTypeChanged = pyqtSignal()

    vesselInstrumentChanged = pyqtSignal()

    def __init__(self, app=None):
        super().__init__()

        # self._logger = logging.getLogger(__name__)
        self._app = app

        self._is_deployed = None
        self._data_path = None

        self._survey_path = r"\\nwcfile\FRAM\Survey.Acoustics"

        self._is_production = False
        self._survey_model = SurveyModel(survey_path=self._survey_path)
        self._survey_model.surveyModelChanged.connect(self._survey_model_changed)
        self._vessel_model = VesselModel()
        self._locations_path = None
        self._raw_path = None
        self._converted_path = None
        self._qaqc_path = None
        self._binned_path = None
        self._source_type = "hex"

        self._status_bar_message = ""

        self._survey = None
        self._vessel = None
        self._instrument = "CTD"

        self._graph_tab = None

        self.surveyChanged.connect(self._set_instrument_path)
        self.vesselChanged.connect(self._set_instrument_path)
        self.instrumentChanged.connect(self._set_instrument_path)

    def _loadSettings(self):
        """
        Method to load the settings.ini file
        :return:
        """
        config = cp.ConfigParser()
        path = os.path.join(os.getcwd(), "settings.ini")
        if os.path.exists(path) and os.path.isfile(path):
            config.read(path)
            if "SETTINGS" in config:
                self._is_deployed = config["SETTINGS"].getboolean('IsDeployed')
                self._data_path = config["SETTINGS"]["DataPath"]
        else:
            self._is_deployed = False
            self._data_path = "C:\\"
            config['SETTINGS'] = {'IsDeployed': self._is_deployed, 'DataPath': self._data_path}
            with open(path, 'w') as configfile:
                config.write(configfile)

        logging.info(f"_load_settings:  _is_deployed = {self._is_deployed}, data_path = {self._data_path}")

    @pyqtProperty(bool, notify=isDeployedChanged)
    def isDeployed(self):
        """
        Method to get the self._is_deployed property.  Used to determine if the software is used at the center
        or in the field
        :return:
        """
        return self._is_deployed

    @isDeployed.setter
    def isDeployed(self, value):
        """
        Method to set the self._is_deployed variable
        :param value:
        :return:
        """
        # logging.info(f"")
        logging.info(f"updating isDeployed to: {value}")

        self._is_deployed = value
        self.isDeployedChanged.emit()

        # Update the settings.ini file
        self._update_ini_file(section="SETTINGS", key="IsDeployed", value=str(value))

        # Update the file listings for the Convert, Graph, and Bin screens
        # self._set_instrument_path()

    @pyqtProperty(str, notify=dataPathChanged)
    def dataPath(self):
        """
        Method to retrieve the self._data_path for the root path for where data is located
        :return:
        """
        return self._data_path

    @dataPath.setter
    def dataPath(self, value):
        """
        Method to set the value of self._data_path, the root path to all of the data files
        :param value:
        :return:
        """
        if "file:///" in value:
            value = value[8:]
            value = value.replace('/', '\\')

        # logging.info(f"")
        logging.info(f"updating dataPath to: {value}")
        self._data_path = value
        self.dataPathChanged.emit()

        # Update the settings.ini file
        self._update_ini_file(section="SETTINGS", key="DataPath", value=str(value))
        self._initialize_data_path_structure()

        # Update the file listings for the Convert, Graph, and Bin screens
        # self._set_instrument_path()

    def _update_ini_file(self, section, key, value):
        """
        Method to update the settings.ini file
        :param section:
        :param key:
        :param value:
        :return:
        """
        if key == "" or value == "":
            return

        config = cp.ConfigParser()
        path = os.path.join(os.getcwd(), "settings.ini")
        if os.path.exists(path) and os.path.isfile(path):
            config.read(path)

        if section != "":
            config[section][key] = value
        else:
            config[key] = value
        with open(path, "w") as configfile:
            config.write(configfile)

    def _initialize_data_path_structure(self):
        """
        Method to create the subdirectories for CTD and UCTD for the given self.dataPath
        :return:
        """
        if self.dataPath is None:
            return

        instruments = ["CTD", "UCTD"]
        paths = ["0_raw", "1_converted", "2_qaqc", "3_final_native", "4_final_binned_1m"]
        for i in instruments:
            if not os.path.exists(os.path.join(self.dataPath, i)):
                os.mkdir(os.path.join(self.dataPath, i))
            for p in paths:
                if not os.path.exists(os.path.join(self.dataPath, i, p)):
                    os.mkdir(os.path.join(self.dataPath, i, p))

    @pyqtProperty(str, notify=graphTabChanged)
    def graphTab(self):
        """
        Method to return the self._graph_tab.  This is used
        for capturing the keyboard press events on the graphs, by
        indicating which graph is the active graph
        :return:
        """
        return self._graph_tab

    @graphTab.setter
    def graphTab(self, value):
        """
        Method to specify the self._graph_tab
        :param value:
        :return:
        """
        self._graph_tab = value
        self.graphTabChanged.emit()

    @pyqtProperty(bool, notify=isProductionChanged)
    def isProduction(self):
        """
        Method indicating if the mode is production or not
        :return:
        """
        return self._is_production

    @isProduction.setter
    def isProduction(self, value):
        """
        Method to set the self._is_production mode to true or false
        :param value:
        :return:
        """
        if not isinstance(value, bool):
            return

        self._is_production = value
        self.isProductionChanged.emit()

        if self._is_production:
            self.path = os.path(r"\\nwcfram\FRAM\Survey.Acoustics")
        else:
            self.path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                     r"data\sbe9plus")

        logging.info(f"path={self.path}")

    @pyqtProperty(FramListModel, notify=surveyModelChanged)
    def surveyModel(self):
        """
        Method to get the currently selected cruise
        :return:
        """
        return self._survey_model

    def _survey_model_changed(self):
        """
        Method called when the underlying self._survey_model has changed
        :return:
        """
        self.surveyModelChanged.emit()

    @pyqtProperty(FramListModel, notify=vesselModelChanged)
    def vesselModel(self):
        """
        Method to get the currently selected vessel
        :return:
        """
        return self._vessel_model

    @pyqtProperty(QVariant, notify=locationsPathChanged)
    def locationsPath(self):
        """
        Method to set the self._ctd_path.  This is the root path for CTD data
        :return:
        """
        return self._locations_path

    @locationsPath.setter
    def locationsPath(self, value):
        """
        Method to set the self._ctd_path
        :param value:
        :return:
        """
        self._locations_path = value
        self.locationsPathChanged.emit()

    @pyqtProperty(QVariant, notify=rawPathChanged)
    def rawPath(self):
        """
        Method to return the self._raw_path
        :return:
        """
        return self._raw_path

    @rawPath.setter
    def rawPath(self, value):
        """
        Method to set the self._raw_path
        :param value:
        :return:
        """
        if isinstance(value, QJSValue):
            value = value.toVariant()
        try:
            self._raw_path = value
            self.rawPathChanged.emit()

        except Exception as ex:
            logging.error(f"Error finding the raw data path: {ex}")
            return

    @pyqtProperty(QVariant, notify=convertedPathChanged)
    def convertedPath(self):
        """
        Method to return the self._converted_path_path
        :return:
        """
        return self._converted_path

    @convertedPath.setter
    def convertedPath(self, value):
        """
        Method to set the self._raw_path
        :param value:
        :return:
        """
        if isinstance(value, QJSValue):
            value = value.toVariant()
        try:
            self._converted_path = value
            self.convertedPathChanged.emit()

        except Exception as ex:
            logging.error(f"Error finding the converted data path: {ex}")
            return

    @pyqtProperty(QVariant, notify=qaqcPathChanged)
    def qaqcPath(self):
        """
        Method to return the QA/QC path
        :return:
        """
        return self._qaqc_path

    @qaqcPath.setter
    def qaqcPath(self, value):
        """
        Method to set the qa/qc path
        :param value:
        :return:
        """
        if isinstance(value, QJSValue):
            value = value.toVariant()
        try:
            self._qaqc_path = value
            self.qaqcPathChanged.emit()

        except Exception as ex:
            logging.error(f"Error finding the qaqc data path: {ex}")
            return

    @pyqtProperty(QVariant, notify=binnedPathChanged)
    def binnedPath(self):
        """
        Method to return the self._binned_path
        :return:
        """
        return self._binned_path

    @binnedPath.setter
    def binnedPath(self, value):
        """
        Method to set the self._binned_path
        :param value:
        :return:
        """
        if isinstance(value, QJSValue):
            value = value.toVariant()

        try:
            self._binned_path = value
            self.binnedPathChanged.emit()
        except Exception as ex:
            logging.error(f"Error setting the binned data path: {ex}")
            return

    @pyqtProperty(QVariant, notify=sourceTypeChanged)
    def sourceType(self):
        """
        Method to return the self._source_type that specifies the type of input file
        This could be one of the following types:
        - hex
        - cnv
        - csv
        :return:
        """
        return self._source_type

    @sourceType.setter
    def sourceType(self, value):
        """
        Method to set the self._source_type
        :param value:
        :return:
        """
        if not isinstance(value, str):
            logging.error(f"Source Type is not a string: {value}")
            return

        self._source_type = value

        # Repopulate the rawPath
        if self._raw_path:
            base_path = os.path.dirname(self._raw_path)
            if "1_converted" in base_path:
                base_path = os.path.dirname(base_path)

            if value in ["hex", "asc"]:
                self.rawPath = os.path.join(base_path, "0_raw")
            elif value == "cnv":
                self.rawPath = os.path.join(base_path, "1_converted", "cnv_files")
            elif value == "csv":
                self.rawPath = os.path.join(base_path, "1_converted", "csv_files")

        self.sourceTypeChanged.emit()

    @pyqtProperty(str, notify=statusBarMessageChanged)
    def statusBarMessage(self):
        """
        Method to return the self._status_bar_message
        :return:
        """
        return self._status_bar_message

    @statusBarMessage.setter
    def statusBarMessage(self, value):
        """
        Method to set the self._status_bar_message
        :param value:
        :return:
        """
        self._status_bar_message = value
        self.statusBarMessageChanged.emit()

    @pyqtSlot()
    def stop_all_threads(self):
        """
        Methohd to stop all of the threads when the window is closed
        :return:
        """
        if self._survey_model._worker:
            self._survey_model._worker.stop()
        if self._app.convert_screen.filesModel._worker:
            self._app.convert_screen.filesModel._worker.stop()
        if self._app.convert_screen._convert_worker:
            self._app.convert_screen._convert_worker.stop()
        if self._app.graph_screen.filesModel._worker:
            self._app.graph_screen.filesModel._worker.stop()
        if self._app.bin_screen.filesModel._worker:
            self._app.bin_screen.filesModel._worker.stop()

    @pyqtSlot(name="setInstrumentPath")
    def _set_instrument_path(self):
        """
        Method to set the instrument path
        :return:
        """
        self.stop_all_threads()

        if self.isDeployed:
            path = os.path.join(self.dataPath, self.instrument)
        elif self.survey and self.vessel and self.instrument:
            path = os.path.join(self._survey_path, self.survey, f"Data_{self.vessel}",
                                r"Ocean & Env", self.instrument)
        else:
            path = None

        logging.info(f"_set_instrument_path, path = {path}, isDeployed = {self.isDeployed}")
        paths = ["0_raw", "1_converted", "2_qaqc", "4_final_binned_1m", "locations"]
        self.rawPath = self.convertedPath = self.qaqcPath = self.binnedPath = self.locationsPath = None

        if path and (self.vessel != "Select Vessel" or self.isDeployed):
            for p in paths:
                current_path = None
                if path:
                    current_path = os.path.join(path, p)
                logging.info(f"\tsetting paths:  {p} >>> {current_path}")
                if p == "0_raw":
                    self.rawPath = current_path
                elif p == "1_converted":
                    self.convertedPath = current_path
                elif p == "2_qaqc":
                    self.qaqcPath = current_path
                elif p == "4_final_binned_1m":
                    self.binnedPath = current_path
                elif p == "locations":
                    locs_files = [f for f in glob.glob(os.path.join(path, r"*locs.xlsx"))]
                    if len(locs_files) > 0:
                        self.locationsPath = os.path.join(path, locs_files[0])
                    logging.info(f"\tlocs_files={locs_files}")

        # Update the file listings for the Convert, Graph, and Bin screens
        self._update_file_listings()

    @pyqtSlot(name="updateFileListings")
    def _update_file_listings(self):
        """
        Method to refresh the convert, graph, and bin file listings
        :return:
        """

        logging.info(f"_update_file_listings")
        # logging.info(f"\trawPath = {self.rawPath}, qaqcPath = {self.qaqcPath}, binPath = {self.binnedPath}")

        self.vesselInstrumentChanged.emit()

        # Update the ConvertScreen.filesModel
        if self.rawPath:
            self._app.convert_screen.filesModel.populate(source_type=self.sourceType)
        else:
            logging.info(f"\tClearing ConvertScreen file list")
            self._app.convert_screen.filesModel.clear()

        # Update the GraphScreen.filesModel
        if self.qaqcPath:
            self._app.graph_screen.filesModel.populate()
            self._app.graph_screen.variablesModel.populate(instrument=self.instrument)
        else:
            logging.info(f"\tClearing GraphScreen file list")
            self._app.graph_screen.filesModel.clear()

        # Update the BinScreen.filesModel        logging.info(f"before BinScreen")
        if self.binnedPath:
            self._app.bin_screen.filesModel.populate()
        else:
            logging.info(f"\tClearing BinScreen file list")
            self._app.bin_screen.filesModel.clear()

    @pyqtProperty(str, notify=instrumentChanged)
    def instrument(self):
        """
        Method to return the self._instrument variable
        :return:
        """
        return self._instrument

    @instrument.setter
    def instrument(self, value):
        """
        Method to set the self._instrument value
        :param value:
        :return:
        """
        if value is None or value == "":
            return

        if not isinstance(value, str):
            logging.error(f"Unable to update the instrument type, not a string: {value}")
            return

        # Determine the source_type for the convert_screen
        if value == "CTD":
            self.sourceType = "hex"
        elif value == "UCTD":
            self.sourceType = "asc"
        elif value == "SBE39":
            self.sourceType = "asc"

        logging.info(f"instrument = {value}")

        self._instrument = value
        self.instrumentChanged.emit()

    @pyqtProperty(str, notify=surveyChanged)
    def survey(self):
        """
        Method to return the self._survey
        :return:
        """
        return self._survey

    @survey.setter
    def survey(self, value):
        """
        Method to set the value of self._survey
        :param value:
        :return:
        """
        if value is None or value == "":
            return

        logging.info(f"survey changed = {value}")

        # Stop all of the directory population threads
        self.stop_all_threads()

        # Repopulate the vessel model
        self.vesselModel.populate(survey=value)

        self._survey = value
        self.surveyChanged.emit()

    @pyqtProperty(str, notify=vesselChanged)
    def vessel(self):
        """
        Method to return the self._vessel
        :return:
        """
        return self._vessel

    @vessel.setter
    def vessel(self, value):
        """
        Method to set the self._vessel variable
        :param value:
        :return:
        """
        if value is None or value == "":
            return

        logging.info(f"vessel changed = {value}")

        self._vessel = value
        self.vesselChanged.emit()

class LoadFilesWorker(QThread):

    loadStatus = pyqtSignal(bool, str)

    def __init__(self, args=(), kwargs=None):
        super().__init__()

        self._is_running = False
        self._app = kwargs["app"]
        self._year = kwargs["year"]
        self._vessel = kwargs["vessel"]

    def run(self):
        self._is_running = True
        status, msg = self.load_records()
        self.loadStatus.emit(status, msg)

    def load_records(self):
        """
        Method called by run.  This actually populates the TableViews in the FileManagementScreen and the
        DataCompletenessScreen.  It is run as a background though so as to be UI responsive when a user  changes
        the year / vessel comboboxes
        :return:
        """

        status = True
        msg = ""

        self._app.file_management.wheelhouseModel.retrieve_items()
        self._app.file_management.backdeckModel.retrieve_items()
        self._app.file_management.sensorsModel.retrieve_items()

        # self._app.data_completeness.dataCheckModel.populate_model()

        msg = "Finished processing records"
        logging.info('finishehd retrieving')
        return status, msg


class TestSettings(unittest.TestCase):
    """
    Test basic SQLite connectivity, properties
    TODO{wsmith} Need to enhance these tests
    """
    def setUp(self):
        db = TrawlAnalyzerDB()
        self.s = Settings(db=db)

    def test_settings(self):

        logging.info('settings: ' + str(self.s._settings))

    def test_printer(self):

        logging.info('printer: ' + self.s._printer)


if __name__ == '__main__':
    unittest.main()

