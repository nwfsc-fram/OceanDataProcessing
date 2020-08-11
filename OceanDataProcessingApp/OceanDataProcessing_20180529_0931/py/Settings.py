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

            # items = list()
            # items.append({"text": "Select Survey"})

            try:

                # logging.info(f"{os.listdir(self._survey_path)}")

                # items = [{"text": os.path.basename(s)} for s in
                #          os.listdir(self._survey_path) if re.search(r'\d{4}\s.*', s) and
                #          os.path.isdir(os.path.join(self._survey_path, s))]
                items = [{"text": os.path.basename(s)} for s in
                         os.listdir(self._survey_path) if
                         s[:4].isdigit() and s[4] == " "
                         and os.path.isdir(os.path.join(self._survey_path, s))]
                items.insert(0, {"text": "Select Survey"})

                # for i, s in enumerate(
                #         [os.path.basename(s) for s in os.listdir(self._survey_path) if re.search(r'\d{4}\s.*', s) and
                #                 os.path.isdir(os.path.join(self._survey_path, s))]):
                #     items.append({"text": s})

                logging.info(f"after adding all survey model items")

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
    surveyModelChanged = pyqtSignal()
    vesselModelChanged = pyqtSignal()
    locationsPathChanged = pyqtSignal()
    rawPathChanged = pyqtSignal()
    convertedPathChanged = pyqtSignal()
    qaqcPathChanged = pyqtSignal()
    binnedPathChanged = pyqtSignal()

    # pingStatusReceived = pyqtSignal(str, bool, arguments=['message', 'success'])

    isProductionChanged = pyqtSignal()
    statusBarMessageChanged = pyqtSignal()
    sourceTypeChanged = pyqtSignal()

    vesselInstrumentChanged = pyqtSignal()
    instrumentChanged = pyqtSignal()

    def __init__(self, app=None):
        super().__init__()

        # self._logger = logging.getLogger(__name__)
        self._app = app

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

        self._path = None
        self._status_bar_message = ""

        self._instrument = "CTD"

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

    @pyqtSlot(str, name="changeSurvey")
    def change_survey(self, survey):
        """
        Method called when the survey is changed in the  MainWindow.qml (i.e. the cbSurvey ComboBox is changed
        :param survey: str - representing the name / folder of the survey that was selected
        :return:
        """
        # Stop the filesModel worker
        # self._app.convertScreen.filesModel.stop()
        self.stop_all_threads()

        # Repopulate the vessel model
        self.vesselModel.populate(survey=survey)

    @pyqtSlot(QVariant, name="changeVesselInstrument")
    def change_vessel_instrument(self, values):
        """
        Method to set the paths
        :param values:
        :return:
        """
        if isinstance(values, QJSValue):
            values = values.toVariant()
        try:

            if isinstance(values, dict) and values['survey'] and values['vessel'] and values['instrument']:
                path = os.path.join(self._survey_path, values["survey"], f"Data_{values['vessel']}",
                                              r"Ocean & Env", values['instrument'])
            else:
                path = None

            paths = ["0_raw", "1_converted", "2_qaqc", "4_final_binned_1m", "locations"]
            self.rawPath = self.convertedPath = self.qaqcPath = self.locationsPath = None
            self.binnedPath = None

            logging.info(f"change_vessel_instrument, values = {values}, path = {path}")

            if path and values["vessel"] != "Select Vessel":
                for p in paths:
                    current_path = None
                    if path:
                        current_path = os.path.join(path, p)
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
                        logging.info(f"locs_files={locs_files}")

            # Determine the source_type for the convert_screen
            if values["instrument"] == "CTD":
                self.sourceType = "hex"
            elif values["instrument"] == "UCTD":
                self.sourceType = "asc"
            elif values["instrument"] == "SBE39":
                self.sourceType = "asc"

            # Update the ConvertScreen.filesModel
            logging.info('calling convert screen files model populate')
            self._app.convert_screen.filesModel.populate(source_type=self.sourceType)

            # Update the GraphScreen.filesModel
            self._app.graph_screen.filesModel.populate()
            self._app.graph_screen.variablesModel.populate(instrument=values["instrument"])

            # Update the BinScreen.filesModel
            self._app.bin_screen.filesModel.populate()

            self.vesselInstrumentChanged.emit()

        except Exception as ex:
            logging.error(f"Error finding the data path: {ex}")
            return

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
        if not isinstance(value, str):
            logging.error(f"Unable to update the instrument type, not a string: {value}")
            return

        self._instrument = value
        self.instrumentChanged.emit()

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

