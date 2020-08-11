
"""
Name:        SBEReader.py
Purpose:     Classes to read and parse data from SBE sensors

Author:      Todd.Hay
Email:       Todd.Hay@noaa.gov

Created:     July 6, 2016
License:     MIT
"""

import csv
import logging
import operator
import os
import re
import time
from collections import OrderedDict
import math
import sys
import glob

import arrow
# import altair as alt
import pandas as pd
import numpy as np
import matplotlib as mpl
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import gridspec
import matplotlib.dates as mdates
from matplotlib import animation
from matplotlib.widgets import Cursor
from matplotlib.patches import Rectangle
from matplotlib import ticker
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter
from matplotlib.widgets import RectangleSelector

from dateutil import parser

# Module Libraries

# logging.error(f"starting_script = {starting_script}")
# if starting_script == "SBEReader.py":
#     from SBE9PlusReader import SBE9plusReader
# elif starting_script == "main.py":
#     from py.SBE9PlusReader import SBE9plusReader

from py.SBE9PlusReader import SBE9plusReader
import py.equations as equations
# from SBE9PlusReader import SBE9plusReader

# Third Party Libraries

__author__ = ('Todd.Hay')

# Variables to show for possible plotting - used during the binning process
VARIABLES = ["Depth (m)",
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

class SbeReader:
    """
    General class for reading and parsing a Seabird hex or cnv (Converted) file
    """

    def __init__(self, *args, **kwargs):
        super().__init__()

        if "file" in kwargs:
            self._data_file = kwargs["file"]

        if "raw_content" in kwargs:
            self._raw_data = kwargs["raw_content"]

        self._support_file = None
        self._support_df = None
        if "support_file" in kwargs:
            self.load_support_df(filename=kwargs["support_file"])

        # Files / Folders
        self._data_file = None
        self._xmlcon_file = None
        self._output_folder = None

        # Model Information
        self._model = None
        self._parser = None
        self._line_count = None
        self._output = None
        self._start_date_time = None

        # Variables
        self._start_date_time = None
        self._latitude = None
        self._longitude = None

        # Matplotlib Plots
        self.qml_item = None                    # QML Item
        self.figure = None                      # Matplotlib Figure
        self.canvas = None                      # Matplitlib Canvas
        self.axes = []                          # List of matplotlib axes

    def set_support_df(self, df):
        """
        Method to set the support dataframe that holds the datatime, latitude, longitude values for a
        given cast
        :param df: pandas dataframe
        :return:
        """
        if not isinstance(df, pd.DataFrame):
            logging.error(f"Not a valid dataframe: {ex}")
            return

        self._support_df = df

    def load_support_df(self, filename):
        """
        Method to set the support file.  This is where thee latitude/longitude/start datetimes
        are stored for each of the casts for a given cruise.
        :param filename:
        :return: None
        """
        try:
            if os.path.isfile(filename):
                self._support_file = filename
                root, ext = os.path.splitext(filename)
                if ext[1:] == "csv":
                    self._support_df = pd.read_csv(filename)
                elif ext[1:] in ["xls", "xlsx"]:
                    self._support_df = pd.read_excel(filename)
        except Exception as ex:
            logging.error(f"Error geting the support file: {ex}")

    def read_source_files(self, data_type=None, data_file=None, xmlcon_file=None, output_folder=None):
        """
        Method to read the file, insert the content into the _raw_content variable and get the total
        line count
        :return:
        """
        if not data_type or not data_file or not output_folder:
            return

        self._data_type = data_type
        self._data_file = data_file
        self._output_folder = output_folder
        self._xmlcon_file = xmlcon_file if data_type == "hex" else None

        if not os.path.isfile(self._data_file):
            logging.error("File does not exist: {0}".format(data_file))
            return

        try:
            f = open(data_file, 'r')
            self._line_count = sum(bl.count("\n") for bl in self.blocks(f))
            self._raw_data = f.read()
            f.close()
        except Exception as ex:
            logging.error(f"Error reading the data file: {ex}")
            return

        try:
            self._raw_xmlcon = None
            if data_type == "hex":
                f = open(xmlcon_file, 'r')
                self._raw_xmlcon = f.read()
                f.close()
        except Exception as ex:
            logging.error(f"Error reading the xmlcon file: {ex}")
            return

        self._get_model()

    def _get_model(self):
        """
        Method to determine the type of Seabird model found.  Once this has been found, a model
        subclass is then called to handle subsequent parsing as each product must be parsed differently.

        :return:
        """
        if self._raw_data is None:
            return

        found_model = False
        model = None
        parser = None
        sampling_frequency = 24         # TODO - Default value, should I change this?
        self._start_date_time = None
        self._latitude = None
        self._longitude = None

        kwargs = {"raw_data": self._raw_data,
                  "raw_xmlcon": self._raw_xmlcon,
                  "support_df": self._support_df}

        self._cnv_columns = []


        # Dictionary to capture all of the potential start times.  Later I check to make sure that they are valid
        # chose the start time from a priority ordering of the possible values
        time_types = ["Locations File", "NMEA UTC", "System UTC", "Start Time"]     # This is the priority ordering
        start_times = OrderedDict({x: None for x in time_types})

        # Gather the starting date/time, latitude, and longitude from the support file
        if isinstance(self._support_df, pd.DataFrame) and not self._support_df.empty:
            root, ext = os.path.splitext(os.path.basename(self._data_file))
            # logging.info(f"root={root}, ext={ext}")
            if "_" in root and ext == ".cnv":  # Needed for 2007 cnv data that was processed by Pierce
                root = root.split("_")[0]
            mask = self._support_df.loc[:, "filename"].str.contains(pat=root, case=False)
            df = self._support_df[mask]
            try:
                start_times["Locations File"] = arrow.get(df.iloc[0]["system (UTC)"], "MM/DD/YYYY HH:mm:ss") \
                    .to(tz="US/Pacific")
                self._latitude = df.iloc[0][[x for x in df.columns.values if "latitude" in x][0]]
                self._longitude = df.iloc[0][[x for x in df.columns.values if "longitude" in x][0]]
            except Exception as ex:
                pass

        for i, line in enumerate(self._raw_data.splitlines()):

            if "*END*" in line:
                self._data_start = i + 1
                break

            if "* Sea-Bird " in line and "Data File:" in line and not found_model:

                if "sbe19plus" in line.lower():
                    model = "SBE19plusV2"
                    parser = SBE19plusV2_Parser(**kwargs)
                    sampling_frequency = 4

                elif "sbe 9 " in line.lower():
                    model = "SBE9plus"
                    logging.info(f"model={model}")
                    parser = SBE9plusReader(**kwargs)
                    sampling_frequency = 24

                elif "sbe39" in line.lower():
                    model = "SBE39"
                    parser = SBE39_Parser(**kwargs)
                    sampling_frequency = 1

                found_model = True

            if "* SBE" in line and "SERIAL NO." in line and not found_model:

                logging.info(f"Model Line: {line}")

                if "19plus v 2" in line.lower():
                    model = "SBE19plusV2"
                    parser = SBE19plusV2_Parser(**kwargs)
                    sampling_frequency = 4

                elif "Sea-Bird SBE 9 Data File" in line.lower():
                    model = "SBE9plus"
                    parser = SBE9plusReader(**kwargs)
                    sampling_frequency = 24

                elif "Sea-Bird SBE39 Data File" in line.lower():
                    model = "SBE39"
                    parser = SBE39_Parser(**kwargs)
                    sampling_frequency = 1

                found_model = True

            # Get all of the potential start times
            if line.startswith("* System UTC ="):
                try:
                    start_times["System UTC"] = arrow.get(line, "MMM DD YYYY HH:mm:ss").to(tz="US/Pacific")
                except Exception as ex:
                    pass

            if line.startswith("# start_time ="):
                try:
                    start_times["Start Time"] = arrow.get(line, "MMM DD YYYY HH:mm:ss").to(tz="US/Pacific")
                except Exception as ex:
                    pass

            if line.startswith("* NMEA UTC (Time) ="):
                try:
                     start_times["NMEA UTC"] = arrow.get(line, "MMM DD YYYY HH:mm:ss").to(tz="US/Pacific")
                except Exception as ex:
                    # The NMEA UTC (Time) has two spaces between the date and time
                    try:
                        start_times["NMEA UTC"] = arrow.get(line, "MMM DD YYYY  HH:mm:ss").to(tz="US/Pacific")
                    except Exception as ex:
                        pass

            if not self._latitude:
                if line.startswith("* NMEA Latitude"):
                    linespl = line.split("=")
                    if len(linespl) >= 2:
                        lat = linespl[1]
                        self._latitude = equations.lat_or_lon_to_dd(input_str=lat)

            if not self._longitude:
                if line.startswith("* NMEA Longitude"):
                    linespl = line.split("=")
                    if len(linespl) >= 2:
                        lon = linespl[1]
                        self._longitude = equations.lat_or_lon_to_dd(input_str=lon)

            if self._data_type == "cnv" and line.startswith("# name"):

                elements  = line.split("=")
                if len(elements) >= 2:
                    key = elements[0]
                    value = elements[1]
                    col = int(key.strip('# name'))
                    # logging.info(f"key={key}, value={value} >>>   col={col}")
                    self._cnv_columns.append(f"{value.split(':')[0].strip()}:")

        # Determine the best start time from the potential start times.  Drop times that are in the future as clearly
        # they are bogus
        logging.info(f"Potential start times: {start_times}")
        now = arrow.now()
        start_times = OrderedDict({k: v for k, v in start_times.items() if v is not None and v <= now})
        logging.info(f"now = {now}")
        logging.info(f"Valid start times: {start_times}")

        if len(start_times) > 0:
            self._start_date_time = list(start_times.items())[0][1]

        logging.info(f"start_time={self._start_date_time},  lat={self._latitude},  lon={self._longitude}")

        # Hardcoded for the csv to csv conversion
        if self._data_type == "csv":
            kwargs = {"raw_data": self._raw_data,
                      "raw_xmlcon": self._raw_xmlcon,
                      "support_df": self._support_df}
            model = "SBE9plus"
            parser = SBE9plusReader(**kwargs)
            sampling_frequency = 24

        self._model = model
        self._parser = parser
        self._sampling_frequency = sampling_frequency

    def convert_hex_to_csv(self):
        """
        This method actually iterates through each of the hex data lines and does the following conversion:
        (1) Convert to decimal
        (2) Convert to engineering units
        (3) Perform calculations to obtain derived values

        :return: output:  List of lists containing the converted results
        """
        start_time = time.time()

        output = []
        output.append(self._parser.header)

        hex_lines = self._raw_data.splitlines()

        current_time = self._start_date_time
        time_increment = 1 / self._sampling_frequency
        previous_raw_units_line = []

        for line_no, i in enumerate(range(self._data_start, self._line_count)):

            pos = 0
            raw_units_line = []

            decimal_line = [int(hex_lines[i][j:j + 2], 16)
                            for j in range(0, len(hex_lines[i]), 2)]

            try:

                for key in self._parser.hex_struct:

                    num_bytes = key["bytes"]
                    if "operations" in key:
                        calc_value = 0
                        for row in key["operations"]:
                            if row["op"] and row["place"] is not None and row["value"] is not None:
                                calc_value += row["op"](decimal_line[pos + row["place"]], row["value"])
                            elif row["place"] is not None:
                                calc_value += decimal_line[pos + row["place"]]
                            elif row["op"] and row["value"] is not None:
                                calc_value = row["op"](calc_value, row["value"])

                            elif row["op"] == "bin":
                                # logging.info(f"key name = {key['name']}")

                                if "Voltage output from A/D channels" in key["name"]:
                                    bytes0 = "{0:08b}".format(decimal_line[pos])
                                    bytes1 = "{0:08b}".format(decimal_line[pos+1])
                                    bytes2 = "{0:08b}".format(decimal_line[pos+2])

                                    first_voltage = 5*(1 - (int(bytes0 + bytes1[:4], 2) / 4095))
                                    second_voltage = 5*(1 - (int(bytes1[4:] + bytes2, 2) / 4095))
                                    # logging.info(f"{bytes0}, {bytes1}, {bytes2} >>> {first_voltage}, {second_voltage}")

                                    raw_units_line.append(first_voltage)
                                    raw_units_line.append(second_voltage)
                                    calc_value = None

                                elif key["name"] == "NMEA Latitude/Longitude Parameters":
                                    # Adjust latitude/longitude values to be negative as appropriate
                                    bin_value = "{0:08b}".format(decimal_line[pos])
                                    # Lat
                                    raw_units_line[-2] = - \
                                        raw_units_line[-2] if bin_value[0] == "1" else raw_units_line[-2]
                                    # Lon
                                    raw_units_line[-1] = - \
                                        raw_units_line[-1] if bin_value[1] == "1" else raw_units_line[-1]

                                elif "8MSB" in key["name"]:
                                    # logging.info(f"{pos}, {decimal_line}")
                                    calc_value = "{0:08b}".format(decimal_line[pos])

                                elif "4LSB" in key["name"]:
                                    bin_value = "{0:08b}".format(decimal_line[pos])[0:4]
                                    calc_value = int(raw_units_line[-1] + bin_value, 2)

                    else:
                        calc_value = decimal_line[pos]

                    if calc_value is not None:
                        raw_units_line.append(calc_value)

                    pos += num_bytes

            except Exception as ex:

                logging.error(f"Error in parsing hex file, skipping line: "
                              f"{ex}, line {line_no}, line len: {len(hex_lines[i])} > {hex_lines[i]}")
                continue

            raw_units_line.append(line_no+1)

            engr_units_line = self._parser.convert_raw_to_engr_units(
                raw_data=raw_units_line, previous_data=previous_raw_units_line,
                latitude=self._latitude, longitude=self._longitude
            )

            # Temperature frequency must have been 0, so couldn't continue calculations, skipping the line
            if engr_units_line is None:
                logging.info(f"Error getting the Engineering Units Line, skipping the line")
                continue

            engr_units_line.append(current_time.format("YYYY-MM-DD"))            
            engr_units_line.append(current_time.format("HH:mm:ss.SSSSSS"))

            output.append(engr_units_line)

            previous_raw_units_line = raw_units_line

            if current_time:
                current_time = current_time.shift(seconds=time_increment)

            line_no += 1

            # if i == self._data_start:
            #     logging.info(f"raw line: {hex_lines[i]}")
            #     logging.info(f"raw line split: {[hex_lines[i][j:j+2] for j in range(0, len(hex_lines[i]), 2)]}")
            #     logging.info(f"decimal_line: {decimal_line}")
            #     logging.info(f"raw_units_line: {raw_units_line}")
            #     logging.info(f"engr_units_line: {engr_units_line}\n")
            #     break

        end_time = time.time()

        logging.info(f"Finished parsing, elapsed time: {end_time-start_time:.2f}s")

        # Write data to a csv file
        csv_file = os.path.basename(self._data_file).split(".")[0] + ".csv"
        csv_path = os.path.join(self._output_folder, csv_file)

        with open(csv_path, 'w') as csv_file:
            writer = csv.writer(csv_file, lineterminator="\n", quoting=csv.QUOTE_NONNUMERIC)
            for row in output:
                if row:
                    writer.writerow(row)

        return output

    def convert_cnv_to_csv(self):
        """
        Method to convert Seabird CNV file to a CSV file
        :return:
        """
        logging.info(f"starting cnv to csv conversion")

        # Determine which rows to keep
        col_name_mapping = {
            "Scan #": [], #["scan:"],
            "Time (HH:mm:ss)": ["timeJ:"],        # TODO - I don't really use this afterall
            "Depth (m)": ["depSM:", "depS:"],
            "Pressure (decibar)": ["prDM:", "pr:"],
            "Temperature (degC)": ["t090C:", "t068:"],
            "Temperature (degC) (Secondary)": ["t190C:"],
            "Conductivity (S_per_m)": ["c0S/m:", "c0mS/cm:"],
            "Conductivity (S_per_m) (Secondary)": ["c1S/m:"],
            "Salinity (psu)": ["sal00:"],
            "Salinity (psu) (Secondary)": ["sal11:"],
            "Oxygen (ml_per_l)": ["sbeox0ML/L:"],
            "Oxygen (ml_per_l) (Secondary)": ["sbeox1ML/L:"],
            "Fluorescence (ug_per_l)": ["wetStar:", "flECO-AFL:"],  # Note:  1 mg/m3 = 1 ug/l
            "Latitude": ["latitude:"],
            "Longitude": ["longitude:"],
            "Turbidity (NTU)": [],
            "Altimeter Height (m)": ["altM:"],
            "Sound Velocity (m_per_s) (cm)": ["svCM:", "svC:"],
            "Sound Velocity (m_per_s) (d)": ["svD:", "avgSvD:"],
            "Sound Velocity (m_per_s) (w)": ["svW:"],
            "Date (YYYY-MM-DD)": []
        }

        logging.info(f"header = {self._parser.header}")
        logging.info(f"cnv columns = {self._cnv_columns}")

        final_cols = OrderedDict()
        for i, x in enumerate(self._parser.header):   # e.g. Depth (m), Pressure (decibars), etc.
            possible_cols = col_name_mapping[x]     # e.g. depSM, depS, etc.
            final_cols[x] = None
            for col in possible_cols:
                matches = [y for y in self._cnv_columns if col in y]
                if len(matches) > 0:
                    final_cols[x] = matches[0]
                    break

        logging.info(f"final_cols = {final_cols}")

        # Process each row of data
        # Set up items for processing
        current_time = self._start_date_time
        time_increment = 1 / self._sampling_frequency

        data = list()
        lines = self._raw_data.splitlines()
        for i, line_no in enumerate(range(self._data_start, self._line_count)):
            line = lines[line_no]
            data.append([x for x in line.split()])
            # data.append([float(x) if isinstance(x, float) else None for x in line.split()])

        df = pd.DataFrame(data=data, columns=self._cnv_columns)
        df = df.apply(pd.to_numeric, errors="coerce")
        # logging.info(f"df={df.head(5)}")
        df_final = pd.DataFrame(columns=self._parser.header)

        for k, v in final_cols.items():

            # Columns that do not depend on any v values
            if k == "Time (HH:mm:ss)":
                df_final[k] = [current_time.shift(seconds=x * time_increment).format("HH:mm:ss.SSSSSS")
                               for x in range(len(df))]
                continue
            elif k == "Date (YYYY-MM-DD)":
                df_final[k] = self._start_date_time.format("YYYY-MM-DD")
                continue
            elif k == "Latitude":
                df_final[k] = self._latitude
                continue
            elif k == "Longitude":
                df_final[k] = self._longitude
                continue
            elif k == "Scan #":
                df_final[k] = range(1, len(df) + 1)
                continue

            if v:
                if v == "c0mS/cm:":             # Convert mS/cm to S/M
                    df_final.loc[:, k] = df[v] * 0.1
                else:
                    df_final[k] = df[v]
            else:
                df_final[k] = None

        # logging.info(f"{df_final.head(3)}")
        # logging.info(f"{df_final.loc[0:26, ['Scan #', 'Latitude', 'Date (YYYY-MM-DD)', 'Time (HH:mm:ss)']]}")

        # Write data to a csv file
        csv_file = os.path.basename(self._data_file).split(".")[0] + ".csv"
        csv_path = os.path.join(self._output_folder, csv_file)
        df_final.to_csv(path_or_buf=csv_path, index=False)

    def convert_csv_to_csv(self):
        """
        Method to convert legacy files in csv format to the latest csv format

        Many assumptions are made in this method as it is considered a one-time
        processing method and should not be used again once these initial files
        are converted

        :return:
        """
        logging.info(f"starting csv to csv conversion")

        # Set up items for processing
        current_time = self._start_date_time
        time_increment = 1 / self._sampling_frequency

        col_map = {"depth": "Depth (m)",
                   "temperature": "Temperature (degC)",
                   "salinity": "Salinity (psu)",
                   "event": "Cast"}

        data = list()
        lines = self._raw_data.splitlines()
        for i, line in enumerate(lines):
            row = [x for x in line.split(",")]
            if i == 0:
                header = [x.lower() for x in row]
            else:
                data.append(row)

        df = pd.DataFrame(data=data, columns=header)
        df = df.apply(pd.to_numeric, errors="coerce")
        df_final = pd.DataFrame(columns=self._parser.header)

        self._support_df.columns = [c.lower() for c in self._support_df.columns]

        for k, v in col_map.items():
            df_final[v] = df[k]

        # logging.info(f"supporting df: {self._support_df.head(5)}")

        casts = df["event"].unique()
        for cast in casts:

            mask = (df_final["Cast"] == cast)
            df_cast = df_final[mask].copy()

            mask = (self._support_df["event"] == cast)
            df_sup_cast = self._support_df[mask]

            size = len(df_cast)
            df_cast.loc[:, "Scan #"] = range(1, size + 1)       # Set the Scan #

            dt = arrow.get(df_sup_cast.iloc[0]["drop time"], "M/D/YYYY H:mm")
            df_cast.loc[:, "Date (YYYY-MM-DD)"] = dt.format("YYYY-MM-DD")   # Set the Date
            df_cast.loc[:, "Time (HH:mm:ss)"] = \
                [dt.shift(seconds=x * time_increment).format("HH:mm:ss.SSSSSS")
                               for x in range(size)]                        # Set the Time
            df_cast.loc[:, "Latitude"] = df_sup_cast.iloc[0]["latitude"]    # Set the Latitude
            df_cast.loc[:, "Longitude"] = df_sup_cast.iloc[0]["longitude"]  # Set the Longitude

            csv_path = os.path.join(self._output_folder, f"{cast}.csv")
            df_cast.to_csv(path_or_buf=csv_path, index=False, columns=self._parser.header)
            logging.info(f"cast {cast} saved")

    def plot_results(self, df, graphs):
        """
        Method to plot out a series of X/Y graphs comparing the values to support QA/QC of
        the various data
        :param data:  list of lists of the data
        :param graphs: list of dictionary where each dictionary contains an x and y value
            that indicates the x / y volumes of the data to be plotted
        :return:
        """

        # logging.info(f"Depth min={df.loc[df['Depth (m)'].idxmin()]}, max={df.loc[df['Depth (m)'].idxmax()]}")

        self.figure = plt.figure(num=None, figsize=(12, 8), dpi=120, facecolor='w', edgecolor='k')
        self.figure.canvas.set_window_title('Oceanographic Data QA/QC')
        self.figure.subplots_adjust(wspace=0.5)
        # plt.ion()
        self.axes = list()
        for i, graph in enumerate(graphs):
            x = graph["x"]
            y = graph["y"]
            self.axes.append(self.figure.add_subplot(1,len(graphs),i+1))
            self.axes[i].set_xlabel(x)
            self.axes[i].set_ylabel(y)
            self.axes[i].grid(linestyle="--", linewidth=0.5, color='gray')
            if y == "Depth (m)":
                self.axes[i].invert_yaxis()
                if "Temperature" in x:
                    self.axes[i].invert_xaxis()
            line = self.axes[i].plot(df[x], df[y], visible=True,  # label=type,
                                 marker='o', markersize=3, color='b', zorder=1, picker=True)

        plt.show(block=True)

        return


        # self.qml_item = item
        # self.figure = self.qml_item.getFigure()




        # self.canvas = FigureCanvas(self.figure)
        # self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.canvas.updateGeometry()
        ax = self.figure.add_subplot(111) #, facecolor='lightblue')

        # ax = self.figure.add_subplot(self.gs[i, :], label=k)
        # ax.xaxis_date("US/Pacific")
        # ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S\n%m/%d/%y', tz=tzlocal()))
        # ax.get_xaxis().get_major_formatter().set_scientific(False)
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.5f'))
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.5f'))
        ax.tick_params(labelsize=7)

        ax.yaxis.grid(True)
        ax.xaxis.grid(True)
        # ax.set_xlim(-124.8, -124.6)
        # ax.set_ylim(45.5, 45.6)
        # ax.set_xlim(MIN_LON, MAX_LON)
        # ax.set_ylim(MIN_LAT, MAX_LAT)

        # ax.xaxis.set_ticklabels([])
        self.axes.append(ax)

        self.figure.subplots_adjust(left=0.1, right=0.99, top=1.0, bottom=0.05)

        # self.qml_item.mpl_connect('button_press_event', self.on_press)
        # self.qml_item.mpl_connect('button_release_event', self.on_release)
        # self.qml_item.mpl_connect("motion_notify_event", self.on_motion)
        # self.qml_item.mpl_connect('scroll_event', self.on_scroll)
        # self.qml_item.mpl_connect('figure_leave_event', self.on_figure_leave)

        # self.qml_item.mpl_connect('pick_event', self.on_pick)

    @staticmethod
    def blocks(files, size=65536):
        while True:
            b = files.read(size)
            if not b:
                files.seek(0)
                break
            yield b


if __name__ == '__main__':

    # Setup Logging Format/etc.
    logging.getLogger().setLevel(logging.INFO)
    log_fmt = '%(levelname)s:%(filename)s:%(lineno)s:%(message)s'
    logging.basicConfig(level=logging.DEBUG, filename='../debug.log', format=log_fmt, filemode='w')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter(log_fmt)
    console.setFormatter(formatter)

    starting_script = os.path.basename(sys.argv[0])
    if starting_script == "SBEReader.py":
        logging.getLogger('').addHandler(console)

    # Start gathering the folders
    app_dir = os.path.abspath(os.path.dirname(__file__))
    support_file_name = "ctd_locs.csv"
    support_file = os.path.join(os.path.normpath(os.path.join(app_dir, "..", "data")), support_file_name)

    # Create the SbeReader instance
    kwargs = {"support_file": support_file}
    reader = SbeReader(**kwargs)

    # Gather all of the cruise folders
    MODE = 'prod'
    if MODE == 'prod':
        acoustics_folder = r"Z:\Survey.Acoustics"
        try:
            cruises = [f for f in os.listdir(acoustics_folder) if re.match(r"\d{4}\s.*", f) and
                   os.path.isdir(os.path.join(acoustics_folder, f))]
        except OSError as ex:
                logging.error(f"OSError: {ex}")

    # Create the raw_dir that contains the folder where the raw CTD files exist
    if MODE == 'test':
        ctd_dir = os.path.normpath(os.path.join(app_dir, "..", "data", "sbe9plus"))
        raw_dir = ''
    else:
        # ctd_dir = r'Z:\Survey.Acoustics\2017 Hake Sum SH_NP\Data_SH\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\2015 Hake Sum SH_WER\Data_SH\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\2013 Hake Sum SH_WER\Data_SH\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\2012 Hake Sum SH_WER_FS\Data_SH\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\2011 Hake Sum SH_WER\Data_SH\Ocean & Env\CTD'

        ctd_dir = r'Z:\Survey.Acoustics\2009 Hake Sum MF_WER\Data_MF\Ocean & Env\CTD'

        # ctd_dir = r'Z:\Survey.Acoustics\2007 Hake Sum MF\Data_MF\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\2005 Hake Sum MF\Data_MF\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\2003 Hake Sum WER\Data_WER\Ocean & Env\CTD'

        # ctd_dir = r'Z:\Survey.Acoustics\2001 Hake Sum MF_WER\Data_MF\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\1998 Hake Sum MF_WER\Data_MF\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\1995 Hake Sum MF_WER\Data_MF\Ocean & Env\CTD'
        # ctd_dir = r'Z:\Survey.Acoustics\1992 Hake Sum MF_WER\Data_MF\Ocean & Env\CTD'

        raw_dir = r'0_raw'
    raw_dir = os.path.join(ctd_dir, raw_dir)
    conv_dir = os.path.join(ctd_dir, r'1_converted')
    cnv_dir = os.path.join(conv_dir, "cnv_files")
    csv_dir = os.path.join(conv_dir, "csv_files")
    qaqc_dir = os.path.join(ctd_dir, r'2_qaqc')
    bin_dir = os.path.join(ctd_dir, r'4_final_binned_1m')

    output_folder = os.path.join(ctd_dir, "1_converted")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    graphs = [{"x": "Temperature (degC)", "y": "Depth (m)"},
              {"x": "Temperature (degC) (Secondary)", "y": "Depth (m)"},
              # {"x": "Salinity (psu)", "y": "Depth (m)"},
              {"x": "Temperature (degC)", "y": "Temperature (degC) (Secondary)"},
              {"x": "Salinity (psu)", "y": "Salinity (psu) (Secondary)"}
              ]
    # graphs = [{"x": "Temperature (degC)", "y": "Depth (m)"}]

    # Configuration for what to run
    convert = False
    plot = False
    bin = False

    data_type = "hex"
    active_dir = raw_dir    # Use for processing hex files
    search_str = r'.*\.(hex|raw|asc|cnv)$'

    bin_only = True
    csv_conv_and_bin = True

    if bin_only:
        bin = True
        active_dir = conv_dir  # Use for processing cnv files
        search_str = r'.*\.(csv)$'  # Use for doing binning only
    elif csv_conv_and_bin:
        convert = True
        bin = True
        data_type = "csv"
        active_dir = csv_dir
        search_str = r'.*\.(csv)$'  # Use for doing binning only

    for i, file in enumerate([f for f in os.listdir(active_dir) if re.search(search_str, f)]):

        # if file[-3:] != "hex":
        #     continue

        # if file != 'CTD001.csv':
        #     continue

        # if i <= 84:
        #     continue

        filename, ext = os.path.splitext(os.path.basename(file))

        # Convert the hex data to csv
        if convert:

            # Read in the source files
            data_file = os.path.join(active_dir, file)
            xmlcon_file = os.path.splitext(data_file)[0] + ".xmlcon"
            reader.read_source_files(data_type=data_type, data_file=data_file,
                                     xmlcon_file=xmlcon_file,
                                     output_folder=output_folder)

            # Set the locations / time file
            locs_files = [f for f in glob.glob(os.path.join(ctd_dir, r"*_CTD_locations.csv"))]
            logging.info(f"locs_files={locs_files}")
            if len(locs_files) > 0:
                logging.info(f"loc file: {locs_files[0]}")
                df_locs = pd.read_csv(locs_files[0])
                reader.set_support_df(df=df_locs)

            if data_type == "hex":
                output = reader.convert_hex_to_csv()
            elif data_type == "cnv":
                reader.convert_cnv_to_csv()
            elif data_type == "csv":
                reader.convert_csv_to_csv()

        # Plot the results
        if plot:
            converted_folder = os.path.join(os.path.dirname(raw_dir), r'1_converted')
            converted_file = os.path.join(converted_folder, os.path.splitext(file)[0] + '.csv')
            df = pd.read_csv(converted_file)
            reader.plot_results(df=df, graphs=graphs)

        # Pickle the csv file to a pandas DataFrame
        if bin:
            conv_file = os.path.join(conv_dir, f"{filename}.csv")
            if os.path.isfile(conv_file):
                df = None

                # If pickle does not exist, create it
                if not os.path.isfile(os.path.join(qaqc_dir, f"{filename}.pickle")):

                    df = pd.read_csv(conv_file)
                    if not os.path.exists(qaqc_dir):
                        os.makedirs(qaqc_dir)

                    try:

                        # Add the invalid columns into the dataframe
                        columns = {f"{x} invalid": False for x in VARIABLES}
                        df = df.assign(**columns)

                        # Calculate the descent and add to the dataframe
                        window_size = 5
                        df.loc[:, "Descent Rate (dz_per_dt)"] = df.loc[:, "Depth (m)"]\
                            .diff().rolling(window=window_size, center=True).mean()
                        mask = (df["Descent Rate (dz_per_dt)"] >= 0)
                        df.loc[:, "is_downcast"] = True
                        df.loc[:, "is_downcast"].where(cond=mask, other=False, inplace=True)
                        # logging.info(f"{df.loc[100:110, ['Depth (m)', 'dz_dt', 'is_downcast']]}")

                        # Save the pickle file on disk
                        df.to_pickle(os.path.join(qaqc_dir, f"{filename}.pickle"))

                    except Exception as ex:
                        logging.error(f"Error binning the data file: {ex}")
                        continue

                # Bin the data and save to the binned folder
                output_file = os.path.join(bin_dir, f"{filename}.csv")
                # if not os.path.exists(output_file):

                logging.info(f"Creating binned file: {output_file}")

                if df is None:
                    df = pd.read_pickle(os.path.join(qaqc_dir, f"{filename}.pickle"))
                bin_size = 1  # 1 meter
                # reader.bin_depths(output_file=output_file, df=df, bin_size=bin_size, average=True)

                # else:
                #     logging.info(f"Binned file exists, skipping ... {output_file}")
