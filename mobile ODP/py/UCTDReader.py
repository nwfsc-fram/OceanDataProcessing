"""
Name:        UCTDReader.py
Purpose:     Classes to read and parse data from Underway CTD sensors

Author:      Todd.Hay
Email:       Todd.Hay@noaa.gov

Created:     September 27, 2017
License:     MIT
"""
__author__ = ('Todd.Hay')

# Python standard libraries
import os
import sys
import logging
import re
import time
import csv
import glob
import math

# Third party libraries
import arrow
from dateutil import tz
import pandas as pd
import numpy as np
from scipy import signal, interpolate
import matplotlib.pyplot as plt

# Project-specific libraries
import py.equations as equations
from py.qaqc import set_downcast
from py.seawater import sw_salt, sw_prandtl, sw_c3515, sw_cndr, sw_dens, sw_pden

OUTPUT_COLUMNS = ["Depth (m)", "Salinity (psu)",
                   "Sound Velocity (m_per_s) (cm)", "Sound Velocity (m_per_s) (d)", "Sound Velocity (m_per_s) (w)",
                   "Latitude", "Longitude", "Date (YYYY-MM-DD)", "Time (HH:mm:ss)"
                  ]

class UctdReader:
    """
    General class for reading and parsing a Seabird hex or cnv (Converted) file
    """

    def __init__(self, **kwargs):
        super().__init__()

        # if "file" in kwargs:
        #     self._data_file = kwargs["file"]

        # if "raw_content" in kwargs:
        #     self._raw_data = kwargs["raw_content"]

        self._support_df = None
        # if "support_file" in kwargs:
        #     self.set_support_df(filename=kwargs["support_file"])

        self._initialize_cast_values()

    def _initialize_cast_values(self):
        """
        Method to initialize internal values when a new file is read.  This is called upon class instantiation and
        also when a new cast is being read/parsed, for otherwise values (such as latitude/longitude/datetime) from
        a previous cast could potentially be used
        :return:
        """
        logging.info(f"\t\tReinitializing the cast values, i.e. latitude, longitude, start date-time, etc.")
        self._data_file = None
        self._output_folder = None
        self._line_count = None

        self._start_date_time = None
        self._latitude = None
        self._longitude = None

        self._coefficients = None        # Stores Sensor Coefficients
        self._instrument = None
        self._header = None

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

    def set_support_df(self, df=None):
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
        return

        # if not isinstance(filename, str):
        #     logging.error(f"supporting filename is not a string: {filename}")
        #     return
        #
        # try:
        #     if os.path.isfile(filename):
        #         root, ext = os.path.splitext(filename)
        #         if ext[1:] == "csv":
        #             self._support_df = pd.read_csv(filename)
        #         elif ext[1:] in ["xls", "xlsx"]:
        #             self._support_df = pd.read_excel(filename)
        #
        # except Exception as ex:
        #     logging.error(f"Error geting the support file: {ex}")

    def read_file(self, data_file=None, output_folder=None):
        """
        Method to read the file, insert the content into the _raw_content variable and get the total
        line count
        :return:
        """
        if not data_file:
            return

        # Reset all of the values that are used to store items such as the latitude, longitude, date-time, etc.
        #  for the cast
        self._initialize_cast_values()

        self._data_file = data_file
        self._output_folder = output_folder

        if not os.path.isfile(self._data_file):
            logging.error(f"File does not exist: {data_file}")
            return

        try:
            f = open(data_file, 'r')
            self._line_count = sum(bl.count("\n") for bl in self.blocks(f))
            self._raw_data = f.read()
            f.close()
        except Exception as ex:
            logging.error(f"Error reading the data file: {ex}")

    def extract_metadata(self):
        """
        Method to extract the metadata about the sensor to include:
         start date/time, latitude, longitude, sampling rate, version, serial number
         and all of the calibration coefficients from the header of the file
        :return:
        """
        if self._raw_data is None:
            return

        coefficients = dict()
        instrument = dict()
        header = dict()

        instrument_data_found = False
        coefficients_found = False
        temp_coeff_found = False
        pressure_coeff_found = False
        cond_coeff_found = False

        abbrev_map = {"C": "Conductivity (S_per_m)", "T": "Temperature (degC)", "P": "Pressure (decibar)"}

        # instrument_values = {"Lat", "Lon", "Cast", "DeviceType", "Version", "SerialNumber"}

        temp_coeff = {"CalDate", "SerialNumber", "A0", "A1", "A2", "A3"}
        cond_coeff = {"CalDate", "SerialNumber", "G", "H", "I", "J", "PCOR", "TCOR", "SLOPE"}
        pres_coeff = {"CalDate", "SerialNumber", "A0", "A1", "A2", "PTEMP A0", "PTEMP A1", "PTEMP A2",
                      "TC A0", "TC A1", "TC A2", "TC B0", "TC B1", "TC B2",
                      "RANGE", "OFFSET"}

        # Parse elements from the main data file
        previous_line = None
        for i, line in enumerate(self._raw_data.splitlines()):

            # portion after the or is for handling 2017 data that was captured differently
            if "*scan#" in line or \
                    (previous_line is not None and previous_line.startswith("*Cast ") and line == "*") or \
                    (previous_line is not None and previous_line.startswith("*Cast ") and line == ""):
                self._data_start = i + 1
                columns = list(filter(None, line.split(" ")))
                if len(columns) == 4:
                    for i, col in enumerate(columns):
                        elements = col.split("[")
                        if len(elements) == 2:
                            # header[i] = f"{abbrev_map[elements[0]]}_{elements[1].replace('/', '_per_').strip('[]')}"
                            header[i] = f"{abbrev_map[elements[0]]}"
                        else:
                            header[i] = f"{elements[0].strip('*')}"

                # 2017 exception where the term *scan# does not appear in the UCTD asc file at all, hardcode the order
                else:
                    header = {0: "scan#", 1: "Conductivity (S_per_m)", 2: "Temperature (degC)", 3: "Pressure (decibar)"}

                header_len = len(header)
                logging.info(f'header={header} >>> len={header_len}')
                for j, value in enumerate(OUTPUT_COLUMNS):
                    header[j + header_len] = value
                logging.info(f"header = {header}")

                break

            if "*Lat" in line:
                latitude = line.split(" ")[1]
                if len(latitude) > 2:
                    try:
                        self._latitude = float(latitude[0:2]) + float(latitude[2:])/60
                        logging.info(f"cast file latitude found: {self._latitude}")
                    except Exception as ex:
                        logging.error(f"Unable to parse a latitude from the cast file: {ex}")

            if "*Lon" in line:
                longitude = line.split(" ")[1]
                if len(longitude) > 3:
                    try:
                        self._longitude = -(float(longitude[0:3]) + float(longitude[3:])/60)
                        logging.info(f"cast file longitude found: {self._longitude}")
                    except Exception as ex:
                        logging.error(f"Unable to parse a longitude from the cast file: {ex}")

            if "*Cast" in line and len(line.split(" ")) >= 6 and "start" not in line:
                dt = line.split(" ")
                # logging.info(f"dt = {dt}")
                try:
                    self._start_date_time = arrow.get(f"{dt[2]} {dt[3]} {dt[4]} {dt[5]}", "DD MMM YYYY HH:mm:ss",
                                                      tzinfo=tz.gettz('US/Pacific'))
                except Exception as ex:
                    logging.info(f"Unable to parse a start-date-time from the cast file: {ex}")

            if "*ConfigurationData:" in line:
                instrument_data_found = True

            if instrument_data_found:
                if "*DeviceType=" in line:
                    instrument["Device Type"] = line.split("=")[1]
                if "*Version=" in line:
                    instrument["Version"] = line.split("=")[1]
                if "*SerialNumber=" in line:
                    instrument["Serial Number"] = line.split("=")[1]

            if "*sampling rate:" in line:
                instrument["Sampling Rate"] = float(line.split("rate:")[1].replace("Hz", "").strip())

            if "*CalibrationCoefficients:" in line:
                coefficients_found = True

            if coefficients_found:

                if "*Temperature:" in line:
                    temp_coeff_found = True
                    cond_coeff_found = False
                    pressure_coeff_found = False

                    coefficients["Temperature"] = dict()
                    current_dict = coefficients["Temperature"]
                    current_coeff = temp_coeff

                if "*Conductivity:" in line:
                    temp_coeff_found = False
                    cond_coeff_found = True
                    pressure_coeff_found = False

                    coefficients["Conductivity"] = dict()
                    current_dict = coefficients["Conductivity"]
                    current_coeff = cond_coeff

                if "*Pressure:" in line:
                    temp_coeff_found = False
                    cond_coeff_found = False
                    pressure_coeff_found = True

                    coefficients["Pressure"] = dict()
                    current_dict = coefficients["Pressure"]
                    current_coeff = pres_coeff

                if temp_coeff_found or cond_coeff_found or pressure_coeff_found:

                    line_split = line.split("=")
                    if line_split[0][1:] in current_coeff and len(line_split) >= 2:
                        if line_split[0][1:] not in ["CalDate", "SerialNumber"]:
                            line_split[1] = float(line_split[1])
                        current_dict[line_split[0][1:]] = line_split[1]

            previous_line = line

        # If the sampling rate is not found (e.g. any of the 2017 data), hardcode it in
        if "Sampling Rate" not in instrument:
            instrument["Sampling Rate"] = 16

        # Parse elements from the self._support_df file for latitude, longitude, and time for the cast
        if isinstance(self._support_df, pd.DataFrame) and not self._support_df.empty:
            cast_file = os.path.basename(self._data_file).lower()
            mask = self._support_df.loc[:, "filename"].str.contains(pat=cast_file, case=False)
            df = self._support_df[mask]
            logging.info(f"{df}")
            try:
                self._latitude = df.iloc[0][[x for x in df.columns.values if "latitude" in x][0]]
                self._longitude = df.iloc[0][[x for x in df.columns.values if "longitude" in x][0]]
                self._start_date_time = arrow.get(df.iloc[0]["gps time (UTC)"], "MM/DD/YYYY HH:mm:ss") \
                    .to(tz="US/Pacific")
            except Exception as ex:
                logging.error(f"Error retrieving the datetime, latitude, longitude from the support file: {ex}")

            logging.info(f"{self._start_date_time}, {self._latitude}, {self._longitude}")

        self._header = header
        self._coefficients = coefficients
        self._instrument = instrument

    def parse_data(self, output="memory"):
        """
        Overarching method to parse the header and data lines
        :param output: Str - enumerated list including:  memory, sqlite
        :return: status - bool - whether the parsing was successful or not
        """
        status = False

        logging.info(f"lat = {self._latitude}, type = {type(self._latitude)}")

        if self._latitude is None or np.isnan(self._latitude):
            logging.error(f"Latitude is not found, skipping processing this cast")
            return status
        if self._longitude is None or np.isnan(self._longitude):
            logging.error(f"Longitude is not found, skipping processing this cast")
            return status
        if self._start_date_time is None:
            logging.error(f"Start Date/Time is not found, skipping processing this cast")
            return status

        start_time = time.time()

        output = list()
        output.append([v for k, v in self._header.items()])

        raw_lines = self._raw_data.splitlines()

        time_increment = 1 / self._instrument["Sampling Rate"]

        # Determine the current_time
        current_time = None
        if self._start_date_time:
            current_time = arrow.get(self._start_date_time)
        # elif "DateTime" in self._instrument:
        #     current_time = arrow.get(self._instrument["DateTime"])

        if current_time is None:
            logging.info(f"\t\tDateTime is not available, skipping parsing")
            return status

        for i in range(self._data_start, self._line_count+1):

            # Skip blank lines at the end of the file
            if i >= len(raw_lines):
                continue
            # logging.info(f"{raw_lines[i]}")
            if len(raw_lines[i].split(" ")) == 0:
                continue

            elements = list(filter(None, raw_lines[i].split(" ")))

            # If not all of the data elements are present, skip processing that row (e.g. 2013, UCTD004.asc)
            if len(elements) < 4:
                continue

            conductivity = float(elements[[k for k, v in self._header.items() if "Conductivity" in v][0]])
            pressure = float(elements[[k for k, v in self._header.items() if "Pressure" in v][0]])
            temperature = float(elements[[k for k, v in self._header.items() if "Temperature" in v][0]])

            # Calculate and add the depth
            if self._latitude:
                elements.append(equations.depth(type="salt water",
                                                pressure=pressure,
                                                latitude=self._latitude))
            else:
                elements.append("")

            # Add Salinity
            salinity = equations.salinity(C=conductivity, P=pressure, T=temperature)
            elements.append(salinity)

            # Add Sound Velocities (x3)
            sound_velocity_cm = equations.sound_velocity_chen_and_millero(s=salinity,
                                                                          t=temperature,
                                                                          p=pressure)
            elements.append(sound_velocity_cm)

            sound_velocity_d = equations.sound_velocity_delgrosso(s=salinity,
                                                                  t=temperature,
                                                                  p=pressure)
            elements.append(sound_velocity_d)
            sound_velocity_w = equations.sound_velocity_wilson(s=salinity,
                                                               t=temperature,
                                                               p=pressure)
            elements.append(sound_velocity_w)


            # Add the Date, Time, Latitude, Longitude
            elements.append(self._latitude)
            elements.append(self._longitude)
            elements.append(current_time.format("YYYY-MM-DD"))
            elements.append(current_time.format("HH:mm:ss.SSSSSS"))

            output.append(elements)

            if current_time:
                current_time = current_time.shift(seconds=time_increment)

        end_time = time.time()

        # logging.info(f"\tFinished parsing, elapsed time: {end_time-start_time:.2f}s")

        # Write data to a csv file
        csv_file = os.path.basename(self._data_file).split(".")[0] + ".csv"
        csv_path = os.path.join(self._output_folder, csv_file)
        # csv_path = os.path.splitext(self._data_file)[0] + ".csv"

        with open(csv_path, 'w') as csv_file:
            wr = csv.writer(csv_file, lineterminator="\n", quoting=csv.QUOTE_NONNUMERIC)
            for row in output:
                if row:
                    wr.writerow(row)

        status = True
        return status

    def create_butterworth_filter(self, cutoff_per, samp_per):

        """
        Create a lowpass butterworth filter
        :param cutoff_per:
        :param samp_per: pandas dataframe containing the dt, i.e. the time difference
        :return:
        """
        order = 4

        nyquist_freq = 1 / (2 * samp_per)
        cutoff_freq = (1 / cutoff_per) / nyquist_freq
        b, a = signal.butter(N=order, Wn=cutoff_freq)
        logging.info(f"cutoff_per={cutoff_per}, samp_per={samp_per}, "
                     f"nyquist_freq={nyquist_freq}, cutoff_freq={cutoff_freq}")

        # w, h = signal.freqs(b, a)
        # plt.semilogx(w, 20 * np.log10(abs(h)))
        # plt.title('Butterworth filter frequency response')
        # plt.xlabel('Frequency [radians / second]')
        # plt.ylabel('Amplitude [dB]')
        # plt.margins(0, 0.1)
        # plt.grid(which='both', axis='both')
        # plt.axvline(cutoff_freq, color='green')  # cutoff frequency
        # plt.show()

        return b, a

    def calculate_uctd_conductivity_cell_velocity(self, dpdt):
        """
        Method to calculate the velocity in the conductivity cell
        :param dpdt: dP/dt (decibar/s) = freestream velocity (m/s)
        :return:
        """
        nu = 1.36e-06   # kinematic viscosity of water (m^2/s)
        dl = 0.1725     # distance between the UCTD inlet and output ports (m)
        a = 2e-03       # radius of conductivity cell tube (m)

        # s = 780
        # e = s+5
        # logging.info(f"dpdt={dpdt.loc[s:e]}")

        cell_velocity = ( -8 * nu * dl + (((8 * nu * dl) ** 2) + (a ** 4) * (dpdt ** 2)) ** 0.5) / (a ** 2)

        plot = False
        if plot:
            fig = plt.figure()
            # ax1 = fig.add_subplot(111)
            # y = range(len(cell_velocity))
            plt.plot(dpdt, cell_velocity, 'r-', linewidth=2)
            # min_y = -2
            # max_y = 10
            # buffer = 0.1
            # # ax1.set_ylim((1 + buffer) * max_y, (1 - buffer) * min_y)
            plt.show()

        return cell_velocity

    def calculate_thermal_mass_coefficients(self, cell_velocity):
        """
        Method to calculate the thermal mass correction coefficients
        :param cell_velocity:
        :return:
        """
        minv = 0.125        # minimum velocity threshold, replace smaller values with this threshold value
        v = cell_velocity.abs()
        v[v < minv] = minv

        alpha = ( 0.0264 / v ) + 0.0492 # 0.0135
        tau = (2.7858 / np.power(v, 0.5)) + 4.032 #+ 7.1499

        return [alpha, tau]

    def compute_gamma(self, C, T, P):
        """
        Method to compute gamma = dC/dT at constant S, P > sensitivity of conductivity to temperature
        :param C:
        :param T:
        :param P:
        :return:
        """
        delta_T = 0.1       # delta temperature for finite-difference estimate of gamma
        C3515 = sw_c3515() / 10
        S = sw_salt(C / C3515, T, P)

        C1 = C3515 * sw_cndr(S=S, T=T + delta_T, P=P)
        C2 = C3515 * sw_cndr(S=S, T=T - delta_T, P=P)

        # logging.info(f"S={S.loc[167:172]}")
        # logging.info(f"T={T.loc[167:172]}")
        # logging.info(f"P={P.loc[167:172]}")

        # logging.info(f"C1={C1.loc[167:172]}")

        gamma = (C1 - C2) / (2 * delta_T)

        return gamma

    def correct_thermal_mass(self, C, T, P, alpha, tau):
        """
        Method to calculate the thermal mass correction
        :param C:
        :param T:
        :param P:
        :param alpha:
        :param tau:
        :return:
        """
        scan_rate = 16
        beta = 1 / tau
        dt = 1 / scan_rate
        a = 2 * alpha / (2 + beta * dt)
        b = 1 - (2 * a / alpha)

        # mask = T.isnull()
        # T_nan = T[mask]
        # logging.info(f"T_nan=\n{T_nan}")

        # Compute conductivity sensitivity to Temperature using mean values
        gamma = self.compute_gamma(C=C, T=T, P=P)
        s = 167
        e = s + 5
        # logging.info(f"gamma = {gamma.loc[s:e]}")
        # logging.info(f"gamma = {gamma.min()}, {gamma.max()}")

        # C_previous = C.shift(1)
        # T_previous = T.shift(1)
        # C_corr = -b * C_previous + a * gamma * (T - T_previous)

        # s = 1000
        # e = s+5

        C_corr = pd.Series(0, index=range(len(C)), dtype='float')
        for i in range(1, len(C)):
            C_corr[i] = -b[i] * C_corr[i-1] + a[i] * gamma[i] * (T[i] - T[i-1])
            if math.isnan(C_corr[i]):
                C_corr[i] = C_corr[i-1]

        C_corr = C_corr + C

        return C_corr

    def create_qaqc_pickle_files(self, input_file, output_folder):
        """
        Method to create the Pandas pickle files that include the invalid columns for marking points as bad or not
        :return:
        """
        try:

            filename = os.path.splitext(os.path.basename(input_file))[0]
            logging.info(f"input_file={input_file}  >>>>  filename={filename}")
            logging.info(f"output_folder={output_folder}")
            df = pd.read_csv(input_file)

            if isinstance(df, pd.DataFrame) and not df.empty:

                # Debugging values, for showing rows of the dataframe
                s = 0
                e = s + 5

                # Add the invalid columns into the dataframe
                extra_columns = ["Temperature (degC)", "Conductivity (S_per_m)", "Pressure (decibar)", "dPdt",
                                 "Seawater Density (kg/m3)", "Sigma Theta"]
                columns = {f"{x} invalid": False for x in extra_columns + OUTPUT_COLUMNS}
                df = df.assign(**columns)

                # Identify the downcast v. upcast by the deepest point
                # If more than one, use the last one as the splitting point
                # TODO Todd Hay - the deepest_idx returns [] when only monotonically increasing, why???
                df = set_downcast(df=df)
                # deepest_idx = df[df["Depth (m)"] == df["Depth (m)"].max()].dropna().index.values
                # logging.info(f"all deepest_idx = {deepest_idx}")
                # if len(deepest_idx) > 0:
                #     deepest_idx = deepest_idx[-1]
                #     logging.info(f"selected deepest depth: {deepest_idx}")
                #
                #     df.loc[:, "is_downcast"] = 0
                #     df.loc[df.loc[:, "is_downcast"].iloc[0:deepest_idx+1].index, "is_downcast"] = 1
                #     # logging.info(f"{df.loc[deepest_idx-2:deepest_idx+3]}")
                # else:
                #     df.loc[:, "is_downcast"] = 1

                # Compute the vertical velocity (dBar/s) from central difference
                df["time"] = pd.DatetimeIndex(pd.to_datetime(df["Date (YYYY-MM-DD)"] + " " +
                                                                  df["Time (HH:mm:ss)"],
                                                                  format="%Y-%m-%d %H:%M:%S.%f")).astype(np.int64)
                size = len(df)
                df['dp'] = df['Pressure (decibar)'].rolling(window=3, center=True).apply(lambda x: x[2] - x[0])
                df.loc[0, 'dp'] = df.loc[1, 'dp']
                df.loc[size-1, 'dp'] = df.loc[size-2, 'dp']
                df['dt'] = (df['time'].shift() - df['time']).abs() / (10 ** 9)
                df['dpdt'] = df['dp'] / (2* df['dt'])
                df.loc[0, 'dpdt'] = df.loc[1, 'dpdt']                               # Fill in the first value
                df.loc[len(df)-1:len(df)+1, 'dpdt'] = df.loc[len(df)-2, 'dpdt']     # Fill in the last two values

                # Low pass filter vertical velocity and pressure
                lpf_vv_p = True
                if lpf_vv_p:
                    samp_per = df.iloc[1]['dt']         # units = seconds = 0.0625 seconds
                    vertical_velocity_cutoff_per = 2    # units = seconds = 2 seconds
                    [b, a] = self.create_butterworth_filter(cutoff_per=vertical_velocity_cutoff_per, samp_per=samp_per)
                    df['dpdt_f'] = signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['dpdt'])))
                    df['Pressure (decibar)'] = signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Pressure (decibar)'])))
                    df['dPdt'] = df['dpdt_f'].copy()

                    # Make plots
                    plot = False
                    if plot:
                        fig = plt.figure()
                        ax1 = fig.add_subplot(111)
                        mask = (df['is_downcast'] == 1)
                        df_masked = df[mask]
                        plt.plot(df_masked['dpdt'], df_masked['Pressure (decibar)'], 'b-')
                        plt.plot(df_masked['dPdt'], df_masked['Pressure (decibar)'], 'r-', linewidth=2)
                        plt.xlabel('Vertical Velocity (dp/dt)')
                        plt.ylabel("Pressure (decibar)")
                        plt.legend(['Original', 'Filtered'])
                        plt.title("Vertical Velocity v. Pressure")
                        min_y = 0
                        max_y = 120
                        buffer = 0.1
                        ax1.set_ylim((1 + buffer) * max_y, (1 - buffer) * min_y)
                        plt.show()

                # Low pass filter temperature and conductivity
                lpf_t_c = True
                if lpf_t_c:
                    T_before = df["Temperature (degC)"].copy()
                    C_before = df["Conductivity (S_per_m)"].copy()
                    ct_filter_cutoff_per = 4*0.0625     # units = seconds, 0.25 seconds
                    [b, a] = self.create_butterworth_filter(cutoff_per=ct_filter_cutoff_per, samp_per=samp_per)
                    df['Temperature (degC)'] = \
                        signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Temperature (degC)'])))
                    df['Conductivity (S_per_m)'] = \
                        signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Conductivity (S_per_m)'])))

                    # logging.info(f"Before low pass filter, C=\n{C_before.loc[s:e]}")
                    # logging.info(f"After low pass filter, C=\n{df.loc[s:e, 'Conductivity (S_per_m)']}")


                    # Make plots
                    plot = False
                    if plot:
                        x = "Conductivity (S_per_m)"
                        fig = plt.figure()
                        ax1 = fig.add_subplot(111)
                        mask = (df['is_downcast'] == 1)
                        df_masked = df[mask]
                        T_before_masked = T_before[mask]
                        C_before_masked = C_before[mask]
                        plt.plot(C_before_masked, df_masked['Pressure (decibar)'], 'b-')
                        plt.plot(df_masked[f"{x}"], df_masked['Pressure (decibar)'], 'r-', linewidth=0.5)
                        plt.xlabel(f"{x}")
                        plt.ylabel("Pressure (decibar)")
                        plt.legend(['Original', 'Filtered'])
                        plt.title(f"{x} v. Pressure")
                        min_y = 0
                        max_y = 120
                        buffer = 0.1
                        ax1.set_ylim((1 + buffer) * max_y, (1 - buffer) * min_y)
                        plt.show()

                # Calculate temperature lag value as a function of filtered vertical velocity
                temp_lag = True
                if temp_lag:
                    lag = [-0.810183190037050, -0.190621249755835, 0.126805428457073, 0.458221237250753, 0.715608325448966,
                           0.886935565443651, 1.00134464049720, 1.08154805953019, 1.13757483933325, 1.15449025724993,
                           1.21413817218518, 1.24662487047467, 1.27898261283749, 1.29319799601310]
                    vvbin = [0.5 + 0.25 * x for x in range(1, 15)]
                    f = interpolate.interp1d(x=vvbin, y=lag, kind='linear', fill_value='extrapolate')
                    lagval = f(df['dPdt'])
                    T_prealign = df["Temperature (degC)"].copy()
                    scan = range(1, len(df)+1)
                    scan_interp = scan + lagval
                    f2 = interpolate.interp1d(x=scan, y=df["Temperature (degC)"], fill_value='extrapolate')
                    df.loc[:, "Temperature (degC)"] = f2(scan_interp)

                    plot_align = False
                    if plot_align:
                        fig = plt.figure()
                        ax1 = fig.add_subplot(111)
                        mask = (df['is_downcast'] == 1)
                        df_masked = df[mask]
                        t_prealign_mask = T_prealign[mask]
                        plt.plot(df_masked['Temperature (degC)'], df_masked['Pressure (decibar)'], 'b-')
                        plt.plot(t_prealign_mask, df_masked['Pressure (decibar)'], 'r-', linewidth=0.5)
                        plt.xlabel('Temperature (degC)')
                        plt.ylabel("Pressure (decibar)")
                        plt.legend(['Aligned', 'Unaligned'])
                        plt.title("Temperature v. Pressure")
                        min_y = 0
                        max_y = 120
                        buffer = 0.1
                        ax1.set_ylim((1 + buffer) * max_y, (1 - buffer) * min_y)
                        plt.show()

                # Correct temperature for viscous heating using Seabird empirical equation
                visc_heat = True
                if visc_heat:
                    T_before = df["Temperature (degC)"].copy()
                    c3515 = sw_c3515() / 10     # Reference conductivity value
                    salt = sw_salt(df["Conductivity (S_per_m)"] / c3515, df["Temperature (degC)"], df["Pressure (decibar)"])
                    prandtl_number = sw_prandtl(T=df["Temperature (degC)"], S=salt)
                    dT = 0.8e-04 * (prandtl_number ** 0.5) * (df['dPdt'] ** 2)
                    df['Temperature (degC)'] = df["Temperature (degC)"] - dT
                    # logging.info(f"Before viscous heat correction, T=\n{T_before.loc[s:e]}")
                    # logging.info(f"After viscous heat correction, T=\n{df.loc[s:e, 'Temperature (degC)']}")

                # Compute thermal mass conductivity cell correction
                thermomass_cell = True
                if thermomass_cell:
                    # Estimate velocity through conductivity cell and use this estimate to the coefficients
                    cell_velocity = self.calculate_uctd_conductivity_cell_velocity(df["dPdt"])
                    # logging.info(f"avg cell veolocity = {cell_velocity.mean()}")

                    # Determine the alpha and tau coefficients
                    [alpha, tau] = self.calculate_thermal_mass_coefficients(cell_velocity=cell_velocity)

                    # logging.info(f"alpha=\n{alpha.iloc[s:e]}")
                    # logging.info(f"tau=\n{tau.iloc[s:e]}")

                    matlab_test = False
                    if matlab_test:
                        df_test = df.copy()
                        df_test["alpha"] = alpha
                        df_test["tau"] = tau
                        invalid_columns = [k for k, v in columns.items()]
                        df_test.drop(["time", "dp", "dt", "dpdt", "dpdt_f", "Depth (m)",
                                      "Salinity (psu)", "Sound Velocity (m_per_s) (cm)",
                                      "Sound Velocity (m_per_s) (d)",
                                      "Sound Velocity (m_per_s) (w)",
                                      "Latitude",
                                      "Longitude",
                                      "Date (YYYY-MM-DD)",
                                      "Time (HH:mm:ss)",
                                      "is_downcast",
                                      "dPdt", "scan#"] + invalid_columns, axis=1, inplace=True)
                        df_test.rename(columns={"Conductivity (S_per_m)": "C", "Temperature (degC)": "T",
                                                "Pressure (decibar)": "P"}, inplace=True)
                        df_test.to_csv(os.path.join(output_folder, f"{filename}.csv"), index=False)

                    C_before = df["Conductivity (S_per_m)"].copy()
                    df.loc[:, "Conductivity (S_per_m)"] = self.correct_thermal_mass(C=df["Conductivity (S_per_m)"],
                                                                                T=df["Temperature (degC)"],
                                                                                P=df["Pressure (decibar)"],
                                                                                alpha=alpha,
                                                                                tau=tau)

                    # logging.info(f"alpha={alpha.loc[s:e]}, tau={tau.loc[s:e]}")
                    # logging.info(f"mean alpha={alpha.mean()}, mean tau={tau.mean()}")
                    # logging.info(f"Before thermomass cell correction, C=\n{C_before.loc[s:e]}")
                    # logging.info(f"After thermomass cell correction, C=\n{df.loc[s:e, 'Conductivity (S_per_m)']}")

                # Compute the updated salinity
                C3515 = sw_c3515()/10
                S_before = df["Salinity (psu)"].copy()
                df.loc[:, "Salinity (psu)"] = sw_salt(R=df["Conductivity (S_per_m)"]/C3515,
                                                      T=df["Temperature (degC)"],
                                                      P=df["Pressure (decibar)"])

                # logging.info(f"Salinity before, S=\n{S_before.loc[s:e]}")
                # logging.info(f"Salinity after, S=\n{df.loc[s:e, 'Salinity (psu)']}")

                # Calculate Sea Water Density
                df.loc[:, "Seawater Density (kg/m3)"] = sw_dens(S=df["Salinity (psu)"],
                                                                T=df["Temperature (degC)"],
                                                                P=df["Pressure (decibar)"])

                # Calculate Sigma_Theta
                pr = 0  # Surface Pressure Reference
                df.loc[:, "Sigma Theta"] = sw_pden(S=df["Salinity (psu)"],
                                                   T=df["Temperature (degC)"],
                                                   P=df["Pressure (decibar)"],
                                                   PR=pr) - 1000
                # logging.info(f"sigma theta")

                # Drop data when sensor is still out of the water, i.e. less than 2 decibar of pressure
                mask = (df["Pressure (decibar)"] <= 2)
                df.loc[mask, [f"{x} invalid" for x in extra_columns]] = True

                # logging.info(f"Pressure invalids\n{df.loc[s:e, ['Pressure (decibar)', 'Pressure (decibar) invalid']]}")

                # Drop extra columns
                df.drop(["time", "dp", "dt", "dpdt", "dpdt_f"], axis=1, inplace=True)
                # logging.info(f"columns={df.columns.values}")

                # Save the pickle file on disk
                df.to_pickle(os.path.join(output_folder, f"{filename}.pickle"))

                return df

        except Exception as ex:
            logging.error(f"Error creating the qaqc pickle file: {ex}")
            return

    def bin_depths(self, output_file=None, df=None, bin_size=1, average=True):
        """
        Method to bin the output by depth size provide by bin_size
        :param output_file: str - full path of the output file that will be created from this process
        :param df: pandas dataframe - the dataframe  that will be binned
        :param bin_size: depth size bin in meters
        :param average: True/False - average within the bins or not
        :return:
        """
        if not isinstance(df, pd.DataFrame):
            logging.error(f"The df variable is not a pandas DataFrame, please try again")
            return

        if isinstance(df, pd.DataFrame) and df.empty:
            logging.error(f"The dataframe is empty, skipping binning")
            return

        if not os.path.isdir(os.path.dirname(output_file)):
            os.makedirs(os.path.dirname(output_file))

        source_col_name = f"Depth (m)"
        binned_col_name = f"Depth Binned ({bin_size}m)"
        max_depth = math.floor(df['Depth (m)'].max())
        bin_size = int(bin_size)
        bins = [x for x in range(0, max_depth+2, bin_size)]

        try:

            # Remove rows that contain invalid data
            mask = ((~df["Temperature (degC) invalid"]) &
                    (~df["Conductivity (S_per_m) invalid"]) &
                    (~df["Pressure (decibar) invalid"]))
            # rows_before = len(df)
            df = df[mask]
            # rows_after = len(df)
            # logging.info(f"rows before and after dropping invalid data: {rows_before} > {rows_after}")

            # Remove invalid columns
            cols = [x for x in df.columns.values if "invalid" not in x]
            df = df.loc[:, cols]

            # Get the columns that will be averaged
            avg_cols = [x for x in df.columns.values if binned_col_name not in x]
            avg_cols.append("dt")

            # Create a datetime in Epoch format (nanoseconds since Jan 1st, 1970) - used later for datetime averaging
            df.loc[:, "dt"] = pd.DatetimeIndex(pd.to_datetime(df["Date (YYYY-MM-DD)"] + " " +
                                                              df["Time (HH:mm:ss)"],
                                                              format="%Y-%m-%d %H:%M:%S")).astype(np.int64)

            # Split the dataframe into the descrent and ascent portions
            mask = (df["is_downcast"] == 1)
            df_descent = df[mask].copy()
            df_ascent = df[~mask].copy()

            for i, df_item in enumerate([df_descent, df_ascent]):

                # Bin the data by depth
                df_item[binned_col_name] = pd.cut(df_item[source_col_name], bins, right=False, labels=bins[:-1])

                # Average within the bins if average = True
                if average:

                    # Get the scan counts for each depth bin
                    df_scan_counts = df_item.groupby([binned_col_name,], as_index=False).size().reset_index(name="Scans per bin")

                    # Create a datetime in Epoch format (nanoseconds since Jan 1st, 1970 - this will be used for datetime averaging
                    # df_item.loc[:, "dt"] = pd.DatetimeIndex(pd.to_datetime(df_item["Date (YYYY-MM-DD)"] + " " +
                    #                       df_item["Time (HH:mm:ss)"], format="%Y-%m-%d %H:%M:%S")).astype(np.int64)

                    # Perform the averaging
                    df_item = df_item.groupby([binned_col_name,], as_index=False)[avg_cols].mean()

                    # Add scan count
                    df_item.loc[:, "Scans per bin"] = df_scan_counts.loc[:, "Scans per bin"]
                    df_item = df_item[df_item["Scans per bin"] != 0]

                if i == 0:
                    df_output = df_item.copy()
                else:
                    df_item = df_item.sort_values(by=binned_col_name, ascending=False)
                    df_output = pd.concat([df_output, df_item], ignore_index=True)

            # Now that the epoch time has been averaged, convert to a datetime and set the Date and Time columns
            df_output.loc[:, "dt"] = pd.to_datetime(df_output["dt"])
            df_output.loc[:, "Date (YYYY-MM-DD)"] = df_output.loc[:, "dt"].dt.strftime("%Y-%m-%d")
            df_output.loc[:, "Time (HH:mm:ss)"] = df_output.loc[:, "dt"].dt.strftime("%H:%M:%S")

            # Drop extraneous columns
            df_output.drop(["scan#", "dt"], axis=1, inplace=True)

            # Save to csv file
            # TODO Todd Hay - use the to_string method instead with some formatters to provide column-specific precision
            df_output = df_output.round(6)
            logging.info(f"output = {output_file}")
            df_output.to_csv(output_file, index=False)

        except Exception as ex:
            logging.error(f"Error binning the data: {ex}")

    @staticmethod
    def blocks(files, size=65536):
        while True:
            b = files.read(size)
            if not b:
                files.seek(0)
                break
            yield b


if __name__ == '__main__':

    log_fmt = '%(levelname)s:%(filename)s:%(lineno)s:%(message)s'
    logging.basicConfig(level=logging.DEBUG, filename='../debug.log', format=log_fmt, filemode='w')

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter(log_fmt)
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    reader = UctdReader()

    TEST_MODE = False
    if TEST_MODE:
        folder = r"C:\Users\Todd.Hay\Desktop\uctd"
        raw_folder = os.path.join(folder, "0_raw")
        converted_folder = os.path.join(folder, "1_converted")
        qaqc_folder = os.path.join(folder, "2_qaqc")
        bin_folder = os.path.join(folder, "4_final_binned_1m")

        # Create 2_qaqc pickle files
        filename_only = "UCTD001"
        input_file = os.path.join(converted_folder, f"{filename_only}.csv")
        df = reader.create_qaqc_pickle_files(input_file=input_file, output_folder=qaqc_folder)

        # Create 4_binned_1_m csv files
        output_file = os.path.join(bin_folder, f"{filename_only}.csv")
        reader.bin_depths(df=df, output_file=output_file, bin_size=1, average=True)

        sys.exit(0)

    cruise_folders  = [
        # '2012 Hake Sum SH_WER_FS',
        # '2013 Hake Sum SH_WER',
        # '2015 Hake Sum SH_WER',
        '2017 Hake Sum SH_NP'
    ]
    df = None
    uctd_folders = [os.path.join(r'Z:\Survey.Acoustics', x, r'Data_SH\Ocean & Env\UCTD') for x in cruise_folders]
    for folder in uctd_folders:
        logging.info(f"Processing folder: {folder}")
        raw_folder = os.path.join(folder, "0_raw")
        converted_folder = os.path.join(folder, "1_converted")
        qaqc_folder = os.path.join(folder, "2_qaqc")
        bin_folder = os.path.join(folder, "4_final_binned_1m")

        locs_files = [f for f in glob.glob(os.path.join(folder, r"*locs.xlsx"))]
        if len(locs_files) > 0:
            locations_file = os.path.join(folder, locs_files[0])
            logging.info(f"\t\tLocations file: {locations_file}")
            reader.set_support_df(filename=locations_file)

        for i, file in enumerate([f for f in os.listdir(raw_folder) if re.search(r'.*\.(hex|raw|asc|cnv)$', f)]):

            # Testing Only
            # if i == 1:
            #     break

            # if i not in [17, 26, 47]:
            #     continue

            # if i == 2:
            #     break

            # if "2017" in folder and i < 152:
            #     continue

            # if file[-3:] != "asc":
            #     continue

            filename_only = os.path.splitext(file)[0]
            data_file = os.path.join(raw_folder, file)

            # if file not in ["UCTD018.asc", "UCTD027.asc", "UCTD048.asc"]:
            if file not in ["UCTD051.asc"]:
                continue

            logging.info(f"\t\tProcessing file: {data_file}")

            reader.read_file(data_file=data_file, output_folder=converted_folder)
            reader.extract_metadata()

            # Converted to 1_converted csv files
            reader.parse_data()

            # Create 2_qaqc pickle files
            input_file = os.path.join(converted_folder, f"{filename_only}.csv")
            df = reader.create_qaqc_pickle_files(input_file=input_file, output_folder=qaqc_folder)

            # Create 4_binned_1_m csv files
            # if not isinstance(df, pd.DataFrame):
            #     df = pd.read_pickle(os.path.join(qaqc_folder, f"{filename_only}.pickle"))
            #     logging.info(f"{df.columns.values}")
            # output_file = os.path.join(bin_folder, f"{filename_only}.csv")
            # reader.bin_depths(df=df, output_file=output_file, bin_size=1, average=True)

            # logging.info("\n\n")