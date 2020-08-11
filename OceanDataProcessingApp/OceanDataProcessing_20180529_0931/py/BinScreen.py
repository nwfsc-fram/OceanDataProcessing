__author__ = 'Todd.Hay'


# -------------------------------------------------------------------------------
# Name:        BinScreen.py
# Purpose:
#
# Author:      Todd.Hay
# Email:       Todd.Hay@noaa.gov
#
# Created:     March 13, 2018
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
from py.UCTDReader import UctdReader
from py.qaqc import bin_depths


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
            qaqc_path = self._app.settings.qaqcPath
            binned_path = self._app.settings.binnedPath

            # hex_files = [os.path.basename(f) for f in os.listdir(raw_path)
            #              if re.search(f".*\.{self.source_type}$", f, flags=re.IGNORECASE)]

            qaqc_files = [os.path.basename(f) for f in os.listdir(qaqc_path)
                         if re.search(f'.*\.{self.source_type}$', f, flags=re.IGNORECASE)]
            qaqc_name_only = [os.path.splitext(f)[0] for f in qaqc_files]

            for qaqc_file in qaqc_files:
                if not self.is_running:
                    break
                item = {"process": "No", "source": qaqc_file, "output": None,
                        "dateTime": None, "status": None}
                if os.path.splitext(qaqc_file)[0] in qaqc_name_only:
                    root, ext = os.path.splitext(qaqc_file)
                    binned_file = f"{root}.csv"
                    date_time = arrow.get(os.path.getmtime(os.path.join(binned_path, binned_file)))\
                        .to("US/Pacific").format("MM/DD/YYYY HH:mm:ss")
                    item["output"] = binned_file
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

        self.source_type = "pickle"

        self._thread = QThread()
        self._worker = FilesWorker(app=self._app, source_type=self.source_type)
        self._worker.moveToThread(self._thread)
        self._worker.loadStatus.connect(self._load_status_received)
        self._worker.rowFound.connect(self._row_found)
        self._thread.started.connect(self._worker.run)

        self.populate()

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
        logging.info(f"populating...bin filesModel")
        if self._thread.isRunning():
            self._thread.quit()
        if source_type:
            self.source_type = source_type
            self._worker.source_type = source_type
        self.clear()
        self._thread.start()
        logging.info(f'bin thread status: {self._thread.isRunning()}')

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


class BinWorker(QObject):

    binStatus = pyqtSignal(bool, str)
    fileBinned = pyqtSignal(dict)

    def __init__(self, app=None, output_folder=None, bin_variable="Depth (m)", bin_size=1, do_average=True,
                 pickle_files=None):
        super().__init__()
        self._app = app
        self.is_running = True

        self.pickle_files = pickle_files
        self.output_folder = output_folder
        self.bin_variable = bin_variable
        self.bin_size = bin_size
        self.do_average = do_average

        self.uctd_reader = UctdReader()

    def stop(self):

        self.is_running = False

    def run(self):

        try:
            self.is_running = True

            qaqc_path = self._app.settings.qaqcPath
            binned_path = self._app.settings.binnedPath

            for file in self.pickle_files:
                if not self.is_running:
                    break

                root, ext = os.path.splitext(file)

                # Emit a message telling the user that the file is being processed
                item = dict()
                item["source"] = file
                item["output"] = ""
                item["status"] = "Binning..."
                self.fileBinned.emit(item)

                # Convert and bin the current pickle file:
                input_file = os.path.join(qaqc_path, file)
                df = pd.read_pickle(input_file)
                output_file = os.path.join(binned_path, f"{root}.csv")

                if file.startswith("CTD"):

                    df = bin_depths(df=df, bin_size=self.bin_size, average=self.do_average)
                    df.to_csv(output_file, index=False)

                elif file.startswith("UCTD"):

                    # TODO Todd Hay - can't this just be deleted and use the code in the CTD section as I pulled
                    # out bin_depths to the equations file?
                    self.uctd_reader.bin_depths(df=df, output_file=output_file, bin_size=self.bin_size,
                                                average=self.do_average)

                # Update the Convert TableView model
                item["output"] = f"{root}.csv"
                item["dateTime"] = arrow.utcnow().to("US/Pacific").format("MM/DD/YYYY HH:mm:ss")
                item["status"] = "Success"
                logging.info(f"updated item: {item}")
                self.fileBinned.emit(item)

            status = True
            message = "Successful binning of files"

        except Exception as ex:

            status = False
            message = f"Binning files error: {ex}"

        self.binStatus.emit(status, message)


class BinScreen(QObject):
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

        self._bin_thread = QThread()
        self._bin_worker = None

        self._support_file = None
        self._support_df = None
        self._sbe_reader = SbeReader()

    @pyqtProperty(FramListModel, notify=filesModelChanged)
    def filesModel(self):
        """
        Method to return the self._files_model for use in the ConvertScreen.qml as the model for
        the primary TableView
        :return:
        """
        return self._files_model

    @pyqtSlot(str, str, float, bool, name="binFiles")
    def bin_files(self, output_folder, bin_variable, bin_size, do_average):
        """
        Method called from the BinScreen.qml to perform the actual binning of the
        files
        :param output_folder:
        :param bin_variable:
        :param bin_size:
        :param do_average:
        :return:
        """

        pickle_files = [f["source"] for f in self._files_model.items]

        self._bin_worker = BinWorker(app=self._app,
                                     output_folder=output_folder,
                                     bin_variable=bin_variable,
                                     bin_size=bin_size,
                                     do_average=do_average,
                                     pickle_files=pickle_files)
        self._bin_worker.moveToThread(self._bin_thread)
        self._bin_worker.binStatus.connect(self._bin_status_received)
        self._bin_worker.fileBinned.connect(self._file_binned)
        self._bin_thread.started.connect(self._bin_worker.run)
        self._bin_thread.start()

    def _bin_status_received(self, status, message):
        """
        Method called at the end of the binning operation to return the status and any messages
        :param status:
        :param message:
        :return:
        """
        self._bin_thread.quit()
        logging.info(f"bin thread completed: {status} > {message}")

    def _file_binned(self, item):
        """
        Method called when an individual pickle file has been binned and placed in the output folder.
        This catches that result and updates the tableview on the BinScreen.qml
        :param item:
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
