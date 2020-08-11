__author__ = 'Todd.Hay'


# -------------------------------------------------------------------------------
# Name:        FishSampling.py
# Purpose:
#
# Author:      Todd.Hay
# Email:       Todd.Hay@noaa.gov
#
# Created:     Jan 11, 2016
# License:     MIT
#-------------------------------------------------------------------------------
import os
import glob
import logging
import unittest
import re

import arrow
import pandas as pd
from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot, QObject, QVariant, QThread
from PyQt5.QtQml import QJSValue

from py.utilities.FramListModel import FramListModel
from py.SBEReader import SbeReader


class FilesWorker(QObject):

    loadStatus = pyqtSignal(bool, str)
    rowFound = pyqtSignal(dict)

    def __init__(self, app=None, source_type=None, **kwargs):
        super().__init__(**kwargs)
        self._app = app
        self.is_running = True
        self.source_type = source_type

    def stop(self):
        self.is_running = False

    def run(self):

        try:
            self.is_running = True

            items = list()
            raw_path = self._app.settings.rawPath
            converted_path = self._app.settings.convertedPath

            logging.info(f"running = {self.is_running}")

            source_files = [os.path.basename(f) for f in os.listdir(raw_path)
                         if re.search(f".*\.{self.source_type}$", f, flags=re.IGNORECASE)]
            csv_files = [os.path.basename(f) for f in os.listdir(converted_path)
                         if re.search(r'.*\.csv$', f, flags=re.IGNORECASE)]
            csv_name_only = [os.path.splitext(f)[0] for f in csv_files]

            logging.info(f"running={self.is_running},   source_files = {source_files}\n")

            for source_file in source_files:

                if not self.is_running:
                    break
                item = {"process": "No", "source": source_file, "output": None,
                        "dateTime": None, "status": None}
                if os.path.splitext(source_file)[0] in csv_name_only:
                    root, ext = os.path.splitext(source_file)
                    csv_file = f"{root}.csv"
                    date_time = arrow.get(os.path.getmtime(os.path.join(converted_path, csv_file)))\
                        .to("US/Pacific").format("MM/DD/YYYY HH:mm:ss")
                    item["output"] = csv_file
                    item["dateTime"] = date_time
                self.rowFound.emit(item)

            status = True
            message = "Successful loading of model files"

        except Exception as ex:

            status = False
            message = f"Populating files error: {ex}"

        self.loadStatus.emit(status, message)


class FilesModel(FramListModel):

    def __init__(self, app=None, db=None):
        super().__init__()
        self._app = app
        self._db = db
        self.add_role_name(name="process")
        self.add_role_name(name="source")
        self.add_role_name(name="output")
        self.add_role_name(name="dateTime")
        self.add_role_name(name="status")

        self.source_type = "hex"

        self._thread = QThread()
        self._worker = FilesWorker(app=self._app, source_type=self.source_type)
        self._worker.moveToThread(self._thread)
        self._worker.loadStatus.connect(self._load_status_received)
        self._worker.rowFound.connect(self._row_found)
        self._thread.started.connect(self._worker.run)

        # self.populate()

    def stop(self):
        """
        Method to stop the worker
        :return:
        """
        self._worker.stop()
        self.clear()

    @pyqtSlot()
    def populate(self, source_type=None):
        """
        Method to populate the FilesModel by querying the folder to determine which hex and csv
        files already exist for the given survey and vessel that are defined in the
        self._app.settings class instance
        :return:
        """
        if self._thread.isRunning():
            self._worker.stop()
            # self._thread.quit()
            logging.info(f"just quit the thread, source_type={source_type}")
        if source_type:
            self.source_type = source_type
            self._worker.source_type = source_type

        self.clear()
        self._thread.start()

    def _row_found(self, item):
        """
        Method to catch a new row that was found via the worker and add it to this model
        :param item:
        :return:
        """
        if not isinstance(item, dict) or item is None:
            return

        root, ext = os.path.splitext(item['source'])
        if self._worker.is_running and ext[1:].lower() == self.source_type.lower():
            self.appendItem(item=item)

    def _load_status_received(self, status, message):
        """
        Method to catch the signal from the thread for loading the files.  This returns two values:
        - status which is true / false if it was successful or not, and a message
        :param status:
        :param message:
        :return:
        """
        self._thread.quit()


class ConvertWorker(QObject):

    convertStatus = pyqtSignal(bool, str)
    fileConverted = pyqtSignal(dict)

    def __init__(self, app=None, source_files=None, locs_file=None, source_type=None, sbe_reader=None, df=None):
        super().__init__()
        self._app = app
        self.is_running = True

        self.source_type = source_type
        self.source_files = source_files
        logging.info(f"source_type={self.source_type}, source_files={self.source_files}")

        self._sbe_reader = sbe_reader
        if isinstance(df, pd.DataFrame) and not df.empty:
            self._sbe_reader.set_support_df(df=df)

    def stop(self):
        self.is_running = False

    def run(self):

        try:
            self.is_running = True

            raw_path = self._app.settings.rawPath
            converted_path = self._app.settings.convertedPath

            for file in self.source_files:
                if not self.is_running:
                    break

                # Emit a message telling the user that the file is being processed
                item = dict()
                item["source"] = file
                item["output"] = ""
                item["status"] = "Processing..."
                self.fileConverted.emit(item)

                # Convert the current hex file:
                data_file = os.path.join(raw_path, file)
                xmlcon_filename = os.path.splitext(data_file)[0] + ".xmlcon"
                xmlcon_file = os.path.join(raw_path, xmlcon_filename)
                self._sbe_reader.read_source_files(data_type=self.source_type,
                                                   data_file=data_file,
                                                   xmlcon_file=xmlcon_file,
                                                   output_folder=converted_path)
                if self.source_type == "hex":
                    output = self._sbe_reader.convert_hex_to_csv()
                elif self.source_type == "cnv":
                    self._sbe_reader.convert_cnv_to_csv()
                elif self.source_type == "csv":
                    self._sbe_reader.convert_csv_to_csv()

                # Update the Convert TableView model
                root, ext = os.path.splitext(file)
                item["output"] = f"{root}.csv"
                item["dateTime"] = arrow.utcnow().to("US/Pacific").format("MM/DD/YYYY HH:mm:ss")
                item["status"] = "Success"
                logging.info(f"updated item: {item}")
                self.fileConverted.emit(item)

            status = True
            message = "Successful loading of model files"

        except Exception as ex:

            status = False
            message = f"Populating files error: {ex}"

        self.convertStatus.emit(status, message)


class ConvertScreen(QObject):
    """
    Class for the FishSamplingScreen.
    """
    filesModelChanged = pyqtSignal()

    def __init__(self, app=None, db=None):
        super().__init__()

        # self._logger = logging.getLogger(__name__)
        self._app = app
        self._db = db

        self._files_model = FilesModel(app=self._app)

        self._convert_thread = QThread()
        self._convert_worker = None

        self._support_file = None
        self._support_df = None
        self._sbe_reader = SbeReader()

        self._app.settings.sourceTypeChanged.connect(self.set_source_type)

    @pyqtProperty(FramListModel, notify=filesModelChanged)
    def filesModel(self):
        """
        Method to return the self._files_model for use in the ConvertScreen.qml as the model for
        the primary TableView
        :return:
        """
        return self._files_model

    def stop_threads(self):
        """
        Method to stop the filesModel and convert worker background threads
        :return:
        """
        # Stop the FileWorker thread
        if self.filesModel._worker:
            self.filesModel._worker.stop()
        if self._convert_worker:
            self._convert_worker.stop()

    def set_source_type(self):
        """
        Method for changing whether the source file types are hex or cnv.  For the earlier years,
        when the source files were *.dat files, most of the time we have the associated cnv files
        so we can just convert those over to our csv formatted files.
        :return:
        """
        # Stop any running background threads
        self.stop_threads()

        if self._app.settings.rawPath:

            # Repopulate the filesModel
            self.filesModel.populate(source_type=self._app.settings.sourceType)

    @pyqtSlot(str, str, name="convertAll")
    def convert_all(self, source_type, locations_file):
        """
        Method to convert all of the hex filse to csv format
        :param locations_file:
        :return:
        """
        source_files = [f["source"] for f in self._files_model.items]
        self._start_convert_thread(source_type=source_type, locations_file=locations_file,
                                   source_files=source_files)

    @pyqtSlot(str, str, name="convertMissing")
    def convert_missing(self, source_type, locations_file):
        """
        Method to convert all of the hex filse to csv format
        :param locations_file:
        :return:
        """
        source_files = [f["source"] for f in self._files_model.items
                        if f["output"] == "" or f["output"] is None]
        logging.info(f"processing missing: {source_files}")
        self._start_convert_thread(source_type=source_type, locations_file=locations_file,
                                   source_files=source_files)

    @pyqtSlot(str, str, QVariant, name="convertSelected")
    def convert_selected(self, source_type, locations_file, indices):
        """
        Method to convert just those files that have beeen selected in the ConvertScreen tableview
        :param source_type:
        :param locations_file:
        :param indices: list containing the numeric indices of rows selected
        :return:
        """
        if isinstance(indices, QJSValue):
            indices = indices.toVariant()
            indices = [int(x) for x in indices]

        source_files = [self._files_model.get(i)["source"] for i in indices]
        self._start_convert_thread(source_type=source_type, locations_file=locations_file,
                                   source_files=source_files)

    def _start_convert_thread(self, source_type, locations_file, source_files):
        """
        This method is used to start the conversion thread
        :param source_type:
        :param locations_file:
        :param source_files:
        :return:
        """

        # If the support file has not been set, set it and create a dataframe from it
        if self._support_file != locations_file:
            try:
                if os.path.isfile(locations_file):
                    self._support_file = locations_file
                    root, ext = os.path.splitext(locations_file)
                    if ext[1:] == "csv":
                        self._support_df = pd.read_csv(locations_file)
                    elif ext[1:] in ["xls", "xlsx"]:
                        self._support_df = pd.read_excel(locations_file)
            except Exception as ex:
                logging.error(f"Error geting the support file: {ex}")

        self._convert_worker = ConvertWorker(app=self._app,
                                             source_files=source_files,
                                             locs_file=locations_file,
                                             source_type=source_type,
                                             sbe_reader=self._sbe_reader,
                                             df = self._support_df)
        self._convert_worker.moveToThread(self._convert_thread)
        self._convert_worker.convertStatus.connect(self._convert_status_received)
        self._convert_worker.fileConverted.connect(self._file_converted)
        self._convert_thread.started.connect(self._convert_worker.run)
        self._convert_thread.start()

    def _convert_status_received(self, status, message):
        """

        :param status:
        :param message:
        :return:
        """
        self._convert_thread.quit()
        logging.info(f"conversion thread completed: {status} > {message}")

    def _file_converted(self, item):
        """
        Method called when an individual hex file has been converted to csv successfully.
        This catches that result and updates the tableview on the ConvertScreen.qml
        :param hex_file:
        :return:
        """
        index = self._files_model.get_item_index(rolename="source", value=item["source"])
        if index >= 0:
            root, ext = os.path.splitext(item["source"])
            value = f"{root}.csv"
            self._files_model.setProperty(index=index, property="output", value=value)
            if "status" in item:
                self._files_model.setProperty(index=index, property="status", value=item["status"])
            if "dateTime" in item:
                self._files_model.setProperty(index=index, property="dateTime", value=item["dateTime"])


if __name__ == '__main__':
    unittest.main()
