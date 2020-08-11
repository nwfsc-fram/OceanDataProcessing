
"""

"""

# Python Standard Library
import operator
import logging
import xml.etree.ElementTree as etree
from collections import OrderedDict
import sys, os
from copy import deepcopy

# Third Party Libraries
import arrow

# Module Components
# starting_script = os.path.basename(sys.argv[0])
# logging.error(f"starting_script = {starting_script}")
# if starting_script == "SBEReader.py":
#     import common
#     import equations
# elif starting_script == "main.py":
#     import py.common
#     import py.equations

import py.common as common
import py.equations as equations
# import common
# import equations


class SBE9plusReader:

    """
    The purpose of this class is to convert hexadecimal-formatted data lines to a decimal
    format for the SBE9plus model.  Each sensor seems to have a slightly different format
    for the hexadecimal data lines.

    ******************************************************************************************
    SBE9plus
    ******************************************************************************************
    This is the current configuration for the NWFSC 2016 SBE9plus's configured for
    the Integrated Hake Acoustic Survey.  These are the sensors that are dropped into the water
    from the NOAA white boats during the hake survey.

    The goal is to do two conversions for the data lines:
    (1) hexadecimal > decimal conversion
    (2) raw units > engineering units

    Model Line Example:

    * Sea-Bird SBE 9 Data File:

    Data Hexadecimal Line Elements:

    Item                            Variable    Bytes       Data
    ------------                    --------    -----       -----------
    Primary temperature frequency               3           Temperature
    Primary conductivity frequency              3           Conductivity
    Pressure frequency                          3           Pressure
    Secondary temperature freq.                 3           Temperature (2nd)
    Secondary conductivity freq.                3           Conductivity (2nd)
    Voltage output from A/D ch 0-1              3           5 = Oxygen / 6= None
    Voltage output from A/D ch 2-3              3           7 = Turbidity / 8 = Fluorescence
    Voltage output from A/D ch 4-5              3           9 = Altimeter / 10 = None
    Voltage output from A/D ch 6-7              3           11 = Oxygen (2nd) / 12 = None
    NMEA Latitude                               3
    NMEA Longitude                              3
    NMEA Parameters (Lat/Lon Sign)              1
    8MSB Pressure Sensor Temp Comp              1
    4LSB                                        1
    Modulo count                                1
    -------------                   -----       -----       ------------
    Total                                       37

    Example Data Line:
    27F9D71A482D818CBF139F261876AE85CFFFFAEFFF02EFFF64CFFF19073A59BF4240948315

    This line has 74 characters and there are 2 characters / byte, so a total of 37 bytes

    Reference:
    http://www.seabird.com/sites/default/files/documents/9plus_018.pdf, p. 31
    http://www.seabird.com/sites/default/files/documents/Seasave_7.26.8.pdf, p. 146
        This section talks about what most Seabird instruments output and then also 
            mentions the custom output format for the SBE 9plus with SBE 11plus Deck Unit
    http://www.seabird.com/sites/default/files/documents/11plsV2_006.pdf, pp. 17-21,

            KEY KEY KEY, LOOK HERE           p. 66 (Raw Data Output Format Table)

    """
    def __init__(self, **kwargs):
        super().__init__()

        self.raw_data = kwargs["raw_data"]
        self.raw_xmlcon = kwargs["raw_xmlcon"] if "raw_xmlcon" in kwargs else None
        self.support_df = kwargs["support_df"] if "support_df" in kwargs else None

        """
        Get the xmlcon_struct first, as there are details there that define the 
        actual hex structure, things like
        whether NMEA position data is added.  Here are possible entries of interest:

            <Name>SBE 911plus/917plus CTD</Name>
            <FrequencyChannelsSuppressed>0</FrequencyChannelsSuppressed>
            <VoltageWordsSuppressed>0</VoltageWordsSuppressed>
            <ComputerInterface>0</ComputerInterface>
            <!-- 0 == SBE11plus Firmware Version >= 5.0 -->
            <!-- 1 == SBE11plus Firmware Version < 5.0 -->
            <!-- 2 == SBE 17plus SEARAM -->
            <!-- 3 == None -->
            <DeckUnitVersion>0</DeckUnitVersion>
            <ScansToAverage>1</ScansToAverage>
            <SurfaceParVoltageAdded>0</SurfaceParVoltageAdded>
            <ScanTimeAdded>0</ScanTimeAdded>
            <NmeaPositionDataAdded>1</NmeaPositionDataAdded>
            <NmeaDepthDataAdded>0</NmeaDepthDataAdded>
            <NmeaTimeAdded>0</NmeaTimeAdded>
            <NmeaDeviceConnectedToPC>0</NmeaDeviceConnectedToPC>        

        """

        # if "raw_xmlcon" in kwargs:
        if self.raw_xmlcon:
            self.instrument, self.sensors = self._get_xmlcon_structure()
            self.hex_parts = self._get_hex_parts()
            self.raw_positions = dict()
            self.hex_struct = self._get_hex_structure()

        self.header = self._get_output_header()

        # logging.info(f"instrument={self.instrument}")

        # for k, v in self.sensors.items():
        #     logging.info(f"{k}: {v}")
        # logging.info(f"\n")


        # for i, x in enumerate(self.hex_struct):
        #     logging.info(f"{i} > {x}")
        #
        # for k, v in self.raw_positions.items():
        #     logging.info(f"{k} > {v}")

    def _get_xmlcon_structure(self):
        """
        Method to parse the associated xmlcon file that contains all of the calibration coefficients
        :return:
        """
        sensors = dict()
        root = etree.fromstring(self.raw_xmlcon)

        # Convert overall instrument details to a dictionary
        instrument = dict()
        for item in root.find("Instrument"):
            if "SensorArray" in item.tag:
                if "Size" in item.attrib:
                    instrument["SensorArraySize"] = int(item.attrib["Size"])
            else:
                instrument[item.tag] = item.text

        # Convert sensor details to a dictionary
        not_in_use_count = 0
        for sensor in root.iter("Sensor"):
            sensor_dict = dict()
            for sensor_type in sensor:

                sensor_dict["index"] = int(sensor.attrib["index"])
                sensor_dict["type"] = sensor_type.tag
                try:
                    sensor_dict["id"] = int(sensor_type.attrib["SensorID"])
                except Exception as ex:
                    pass

                if sensor_type.tag == "NotInUse":
                    break;

                for item in sensor_type:
                    if item.tag == "Coefficients" or item.tag == "CalibrationCoefficients":
                        coefficients_dict = dict()
                        coefficients_dict["equation"] = int(item.attrib["equation"])
                        for coefficient in item:
                            try:
                                if "date" in coefficient.tag.lower():
                                    coefficients_dict[coefficient.tag] = self._parse_date(coefficient.text)
                                else:
                                    coefficients_dict[coefficient.tag] = float(coefficient.text)
                            except Exception as ex:
                                logging.error(f"Error converting coefficient to float: {coefficient.text} > {ex}")

                        sensor_dict[item.tag + "_" + item.attrib["equation"]] = coefficients_dict
                    else:
                        try:
                            if "date" in item.tag.lower():
                                sensor_dict[item.tag] = self._parse_date(item.text)
                            elif "SerialNumber" in item.tag:
                                sensor_dict[item.tag] = int(item.text)
                            else:
                                sensor_dict[item.tag] = float(item.text)
                        except Exception as ex:
                            logging.error(f"Error converting item: {item.tag}, {item.text} > {ex}")

            if sensor_dict["type"] != "NotInUse":
                if sensor_dict["type"].replace("Sensor", "") in sensors and sensor_dict["index"] > 2:
                    sensors["Secondary" + sensor_dict["type"].replace("Sensor", "")] = sensor_dict
                else:
                    sensors[sensor_dict["type"].replace("Sensor", "")] = sensor_dict
            else:
                sensor_name = f"NotInUse{not_in_use_count}"
                sensors[sensor_name] = sensor_dict
                not_in_use_count += 1

        return instrument, sensors

    def _get_output_header(self):
        """
        Method to return the header for the output csv file
        :return:
        """
        header = ["Scan #", "Depth (m)", "Pressure (decibar)",
                  "Temperature (degC)", "Salinity (psu)",
                  "Temperature (degC) (Secondary)", "Salinity (psu) (Secondary)",
                  "Conductivity (S_per_m)", "Conductivity (S_per_m) (Secondary)",
                  "Sound Velocity (m_per_s) (cm)", "Sound Velocity (m_per_s) (d)", "Sound Velocity (m_per_s) (w)",
                  "Oxygen (ml_per_l)", "Oxygen (ml_per_l) (Secondary)",
                  "Fluorescence (ug_per_l)", "Turbidity (NTU)", "Altimeter Height (m)",
                  "Latitude", "Longitude", "Date (YYYY-MM-DD)", "Time (HH:mm:ss)"]
        return header

    def _get_hex_parts(self):
        """
        Method to create the variable components that will ultimately comprise a data line in the
        Seabird hex file.  These represent the individual sensor measurements, stored as a dictionary.
        The actual ordering of these sensors can changed, and is directed by the order found in the
        xmlcon file.  The association between these parts and the xmlcom structure to give the
        overall line structure is handled in the _get_hex_structure method
        :return:
        """
        parts = OrderedDict()
        parts["Temperature"] = \
            {"bytes": 3, "name": "Primary temperature frequency", "symbol": "F_t", "type": "sensor",
                     "operations": [{"op": operator.mul, "place": 0, "value": 256},
                                    {"op": None, "place": 1, "value": None},
                                    {"op": operator.truediv, "place": 2, "value": 256}]
                     }
        parts["Conductivity"] = \
            {"bytes": 3, "name": "Primary conductivity frequency", "symbol": "F_c", "type": "sensor",
                     "operations": [{"op": operator.mul, "place": 0, "value": 256},
                                    {"op": None, "place": 1, "value": None},
                                    {"op": operator.truediv, "place": 2, "value": 256}]
                     }
        parts["Pressure"] = \
            {"bytes": 3, "name": "Pressure frequency", "symbol": "F_p", "type": "sensor",
             "operations": [{"op": operator.mul, "place": 0, "value": 256},
                            {"op": None, "place": 1, "value": None},
                            {"op": operator.truediv, "place": 2, "value": 256}]
             }
        parts["SecondaryTemperature"] = \
            {"bytes": 3, "name": "Secondary temperature frequency", "type": "sensor",
             "operations": [{"op": operator.mul, "place": 0, "value": 256},
                            {"op": None, "place": 1, "value": None},
                            {"op": operator.truediv, "place": 2, "value": 256}
                            ]
             }
        parts["SecondaryConductivity"] = \
            {"bytes": 3, "name": "Secondary conductivity frequency", "type": "sensor",
             "operations": [{"op": operator.mul, "place": 0, "value": 256},
                            {"op": None, "place": 1, "value": None},
                            {"op": operator.truediv, "place": 2, "value": 256}]
             }
        parts["Voltage Channels 0-1"] = \
            {"bytes": 3, "name": "Voltage output from A/D channels 0-1", "type": "voltage",
             "symbol": "V_01", "channels": [0, 1],
             "operations": [{"op": "bin", "place": None, "value": None}]
             }
        parts["Voltage Channels 2-3"] = \
            {"bytes": 3, "name": "Voltage output from A/D channels 2-3", "type": "voltage",
             "symbol": "V_23", "channels": [2, 3],
             "operations": [{"op": "bin", "place": None, "value": None}]
             }
        parts["Voltage Channels 4-5"] = \
            {"bytes": 3, "name": "Voltage output from A/D channels 4-5", "type": "voltage",
             "symbol": "V_45", "channels": [4, 5],
             "operations": [{"op": "bin", "place": None, "value": None}]
             }
        parts["Voltage Channels 6-7"] = \
            {"bytes": 3, "name": "Voltage output from A/D channels 6-7", "type": "voltage",
             "symbol": "V_67", "channels": [6, 7],
             "operations": [{"op": "bin", "place": None, "value": None}]
             }
        parts["NMEA Latitude"] = \
            {"bytes": 3, "name": "NMEA Latitude", "symbol": "lat", "type": "latlon",
             "operations": [{"op": operator.mul, "place": 0, "value": 65536},
                            {"op": operator.mul, "place": 1, "value": 256},
                            {"op": None, "place": 2, "value": None},
                            {"op": operator.truediv, "place": None, "value": 50000}]
             }
        parts["NMEA Longitude"] = \
            {"bytes": 3, "name": "NMEA Longitude", "symbol": "lon", "type": "latlon",
             "operations": [{"op": operator.mul, "place": 0, "value": 65536},
                            {"op": operator.mul, "place": 1, "value": 256},
                            {"op": None, "place": 2, "value": None},
                            {"op": operator.truediv, "place": None, "value": 50000}]
             }
        parts["NMEA Latitude/Longitude Parameters"] = \
            {"bytes": 1, "name": "NMEA Latitude/Longitude Parameters", "type": "latlon",
             "operations": [{"op": "bin", "place": None, "value": None}]
             }
        parts["8MSB Pressure Sensor Temp Comp"] = \
            {"bytes": 1, "name": "8MSB Pressure Sensor Temp Comp", "type": "other",
             "operations": [{"op": "bin", "place": None, "value": None}]
             }
        parts["Pressure Temp Comp"] = \
            {"bytes": 1, "name": "4LSB Pressure Sensor Temp Comp", "symbol": "PT_comp", "type": "other",
             "operations": [{"op": "bin", "place": None, "value": None}]}
        parts["Modulo Count"] = {"bytes": 1, "name": "Modulo Count", "type": "other"}

        return parts

    def _get_hex_structure(self):
        """
        Method to specify the structure of the hexadecimal data lines based upon the given sensor type

        For the Seabird 9/11, the order is defined in the following two documents:

        Seabird_11pV2_017.pdf - p. 65 - doesn't explicitly list the NMEA elements
        Seabird_Seasave_7.26.8.pdf - p. 146 - This shows the NMEA positions

        Primary Sensors
        Voltages - 0-1, 2-3, 4-5, 6-7
        NMEA Latitude / Longitude / Parameters


        :return: list - containing the data structure
        """
        parser = list()
        sensor_list = sorted(self.sensors, key=lambda x: self.sensors[x]["index"])
        voltage_sensor_start = None
        for sensor in sensor_list:
            self.raw_positions[sensor] = self.sensors[sensor]["index"]

            if sensor in self.hex_parts:

                # Get the primary sensors (Temperature, Conductivity, Pressure, Temperature2, Conductivity2
                parser.append(deepcopy(self.hex_parts[sensor]))

            else:

                # Gather all of the Voltage channels and assign to the appropriate sensors
                if self.sensors[sensor]["index"] < self.instrument["SensorArraySize"]:
                    if voltage_sensor_start is None:
                        voltage_sensor_start = len(parser)
                    channel = self.sensors[sensor]["index"] - voltage_sensor_start
                    parts_key = [k for k, v in self.hex_parts.items() if "channels" in v and channel in v["channels"]]

                    # logging.info(f"channel = {channel},   parts_key = {parts_key}")

                    if len(parts_key) == 1:
                        parts_key = parts_key[0]
                        if self.hex_parts[parts_key] not in parser:
                            parser.append(deepcopy(self.hex_parts[parts_key]))

        # Get the remaining items:  NMEA latitude/longitude/parameters, 8MSB, 4LSB, and modulo count
        raw_pos = self.instrument["SensorArraySize"]
        parts = OrderedDict({k:v for k, v in self.hex_parts.items() if v["type"] in ["latlon", "other"]})
        for k, v in parts.items():

            # TODO Todd Hay - Do the latlon and other items ever get reversed?
            parser.append(deepcopy(v))
            self.raw_positions[k] = raw_pos
            raw_pos += 1

        # TODO Todd Hay - Add If/then flags driven by xmlcon instrument metadata parsing

        return parser

    def _parse_date(self, value):
        """
        Method to parse the various possible date formats provided in the xmlcon file.  So far I have found the following
        possible date formats:

        21-Nov-14       DD-MMM-YY
        24 OCT 2014     DD MMM YYYY
        OCT-24-2014     MMM-DD-YYYY

        :param value:
        :return:
        """
        for date_format in common.DATE_FORMATS:
            try:
                date_value = arrow.get(value, date_format)
            except Exception as ex:
                pass
            else:
                break
        else:
            date_value = None

        return date_value

    def convert_raw_to_engr_units(self, raw_data, previous_data, latitude, longitude):
        """
        Method to convert the raw units to engineering units
        :param raw_data: list containing all of the raw units
        :param previous_data: list containing all of the raw units from the previous row.  This is only
            used for calculations such as the Dissolved Oxygen where a change in voltage is required
        :param latitude: float - latitude in decimal degrees
        :param longitude: float - longitude in decimal degrees
        :return: list containing all of the engineering units
        """
        engr_data = list()
        pos = self.raw_positions

        # Latitude / Longitude Values
        if latitude is None and "NMEA Latitude" in pos:
            latitude = raw_data[pos["NMEA Latitude"]]
        if longitude is None and "NMEA Longitude" in pos:
            longitude = raw_data[pos["NMEA Longitude"]]

        # Pressure
        try:
            pressure = None
            if "Pressure" in pos:
                p = self.sensors["Pressure"]
                pressure = equations.pressure(f=raw_data[pos["Pressure"]],
                                      M=p["AD590M"], B=p["AD590B"], pt_comp=raw_data[pos["Pressure Temp Comp"]],
                                      c1=p["C1"], c2=p["C2"], c3=p["C3"],
                                      t1=p["T1"], t2=p["T2"], t3=p["T3"], t4=p["T4"], t5=p["T5"],
                                      d1=p["D1"], d2=p["D2"], slope=p["Slope"], offset=p["Offset"])
        except Exception as ex:
            logging.error(f"Failed to calculate the pressure: {ex}")

        # Depth
        try:
            depth = None
            if pressure is not None and latitude is not None:
                depth = equations.depth(type="salt water", pressure=pressure, latitude=latitude)
        except Exception as ex:
            logging.error(f"Failed to calculate the pressure: {ex}")

        # Temperature - Primary
        try:
            temperature = None
            if "Temperature" in pos:
                t = self.sensors["Temperature"]
                temperature = equations.temperature(f=raw_data[pos["Temperature"]], g=t["G"], h=t["H"], i=t["I"],
                                            j=t["J"], f0=t["F0"])
        except Exception as ex:
            logging.error(f"Failed to calculate the temperature: {ex}")

        # Temperature - Secondary
        try:
            temperature_secondary = None
            if "SecondaryTemperature" in pos:
                t = self.sensors["SecondaryTemperature"]
                temperature_secondary = equations.temperature(f=raw_data[pos["SecondaryTemperature"]],
                                                      g=t["G"], h=t["H"], i=t["I"],
                                                      j=t["J"], f0=t["F0"])
        except Exception as ex:
            logging.error(f"Failed to calculate the secondary temperature: {ex}")

        # Conductivity - Primary
        try:
            conductivity = None
            if temperature is not None and pressure is not None and "Conductivity" in pos:
                c = self.sensors["Conductivity"]
                if "Coefficients_1" in c:
                    c = c["Coefficients_1"]
                conductivity = equations.conductivity(f=raw_data[pos["Conductivity"]], g=c["G"], h=c["H"], i=c["I"], j=c["J"],
                                              cpcor=c["CPcor"], ctcor=c["CTcor"],
                                              T=temperature, P=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the conductivity: {ex}")

        # Conductivity - Secondary
        try:
            conductivity_secondary = None
            if temperature_secondary is not None and pressure is not None and \
                    "SecondaryConductivity" in pos:
                c = self.sensors["SecondaryConductivity"]
                if "Coefficients_1" in c:
                    c = c["Coefficients_1"]
                conductivity_secondary = equations.conductivity(f=raw_data[pos["SecondaryConductivity"]],
                                                        g=c["G"], h=c["H"], i=c["I"], j=c["J"],
                                                        cpcor=c["CPcor"], ctcor=c["CTcor"],
                                                        T=temperature_secondary, P=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the secondary conductivity: {ex}")

        # Salinity
        try:
            salinity = None
            if conductivity is not None and temperature is not None and pressure is not None:
                salinity = equations.salinity(C=conductivity, T=temperature, P=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the salinity: {ex}")

        try:
            salinity_secondary = None
            if conductivity_secondary is not None and temperature_secondary is not None and \
                pressure is not None:
                salinity_secondary = equations.salinity(C=conductivity_secondary,
                                                    T=temperature_secondary, P=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the secondary salinity: {ex}")

        # Sound Velocity [Chen-Millero, m/s]
        try:
            sound_velocity_cm = None
            if salinity is not None and temperature is not None and pressure is not None:
                sound_velocity_cm = equations.sound_velocity_chen_and_millero(s=salinity, t=temperature, p=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the chen-millero sound velocity: {ex}")

        # Sound Velocity [Delgrosso, m/s]
        try:
            sound_velocity_d = None
            if salinity is not None and temperature is not None and pressure is not None:
                sound_velocity_d = equations.sound_velocity_delgrosso(s=salinity, t=temperature, p=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the delgrosso sound velocity: {ex}")

        # Sound Velocity [Wilson, m/s]
        try:
            sound_velocity_w = None
            if salinity is not None and temperature is not None and pressure is not None:
                sound_velocity_w = equations.sound_velocity_wilson(s=salinity, t=temperature, p=pressure)
        except Exception as ex:
            logging.error(f"Failed to calculate the wilson sound velocity: {ex}")

        # Dissolved Oxygen - First [SBE 43] - without a hysteresis correction
        try:
            oxygen_primary = None
            if salinity is not None and temperature is not None and pressure is not None and \
                    "Oxygen" in pos:
                o = self.sensors["Oxygen"]
                if "CalibrationCoefficients_1" in o:
                    o = o["CalibrationCoefficients_1"]
                previous_voltage = previous_data[pos["Oxygen"]] if previous_data else None
                oxygen_primary = equations.oxygen(temperature=temperature, pressure=pressure, salinity=salinity,
                    voltage=raw_data[pos["Oxygen"]], Soc=o["Soc"], VOffset=o["offset"], A=o["A"], B=o["B"], C=o["C"],
                    E=o["E"], tau20=o["Tau20"], D1=o["D1"], D2=o["D2"], H1=o["H1"], H2=o["H2"], H3=o["H3"],
                    previous_voltage=previous_voltage)
        except Exception as ex:
            logging.error(f"Failed to calculate the oxygen: {ex}")

        # Dissolved Oxygen - Second [SBE 43] - without a hysteresis correction
        try:
            oxygen_secondary = None
            if salinity is not None and temperature is not None and pressure is not None and \
                    "SecondaryOxygen" in pos:
                o = self.sensors["SecondaryOxygen"]
                if "CalibrationCoefficients_1" in o:
                    o = o["CalibrationCoefficients_1"]
                previous_voltage = previous_data[pos["SecondaryOxygen"]] if previous_data else None
                oxygen_secondary = equations.oxygen(temperature=temperature, pressure=pressure, salinity=salinity,
                    voltage=raw_data[pos["SecondaryOxygen"]], Soc=o["Soc"], VOffset=o["offset"], A=o["A"], B=o["B"], C=o["C"],
                    E=o["E"], tau20=o["Tau20"], D1=o["D1"], D2=o["D2"], H1=o["H1"], H2=o["H2"], H3=o["H3"],
                    previous_voltage=previous_voltage)
        except Exception as ex:
            logging.error(f"Failed to calculate the secondary oxygen: {ex}")

        # Turbidity - raw_data[7] / ScaleFactor / DarkVoltage
        try:
            turbidity = None
            if "TurbidityMeter" in pos:
                t = self.sensors["TurbidityMeter"]
                turbidity = equations.turbidity(voltage=raw_data[pos["TurbidityMeter"]], dark_output=t["DarkVoltage"],
                                        scale_factor=t["ScaleFactor"])
        except Exception as ex:
            logging.error(f"Failed to calculate turbidity: {ex}")

        # Fluorescence - raw_data[8] / ScaleFactor / Vblank
        try:
            fluorescence = None
            if "FluoroWetlabECO_AFL_FL_" in pos:
                f = self.sensors["FluoroWetlabECO_AFL_FL_"]
                fluorescence = equations.fluorescence(voltage=raw_data[pos["FluoroWetlabECO_AFL_FL_"]], dark_output=f["Vblank"],
                                              scale_factor=f["ScaleFactor"])
        except Exception as ex:
            logging.error(f"Failed to calculate fluorescence: {ex}")

        # Altimeter - raw_data[9] / ScaleFactor / Offset
        try:
            if "Altimeter" in pos:
                a = self.sensors["Altimeter"]
                altimeter_height = equations.altimeter_height(voltage=raw_data[pos["Altimeter"]],
                                                          scale_factor=a["ScaleFactor"],
                                                          offset=a["Offset"])
        except Exception as ex:
            logging.error(f"Failed to calculate fluorescence: {ex}")


        # Append everything to the output line
        engr_data.append(raw_data[-1])          # Scan #

        engr_data.append(round(depth, 3) if isinstance(depth, float) else None)
        engr_data.append(round(pressure, 3) if isinstance(pressure, float) else None)
        engr_data.append(round(temperature, 4) if isinstance(temperature, float) else None)
        engr_data.append(round(salinity, 4) if isinstance(salinity, float) else None)
        engr_data.append(round(temperature_secondary, 4) if isinstance(temperature_secondary, float) else None)
        engr_data.append(round(salinity_secondary, 4) if isinstance(salinity_secondary, float) else None)
        engr_data.append(round(conductivity, 4) if isinstance(conductivity, float) else None)
        engr_data.append(round(conductivity_secondary, 4) if isinstance(conductivity_secondary, float) else None)

        # Sound Velocities x 3
        engr_data.append(round(sound_velocity_cm, 2) if isinstance(sound_velocity_cm, float) else None)
        engr_data.append(round(sound_velocity_d, 2) if isinstance(sound_velocity_d, float) else None)
        engr_data.append(round(sound_velocity_w, 2) if isinstance(sound_velocity_w, float) else None)

        # Dissolved Oxygen - Primary + Secondary, both are SBE 43s
        engr_data.append(round(oxygen_primary, 4) if isinstance(oxygen_primary, float) else None)
        engr_data.append(round(oxygen_secondary, 4) if isinstance(oxygen_secondary, float) else None)

        # Fluorescence / Turbidity / Altimeter Height
        engr_data.append(round(fluorescence, 4) if isinstance(fluorescence, float) else None)
        engr_data.append(round(turbidity, 4) if isinstance(turbidity, float) else None)
        engr_data.append(round(altimeter_height, 4) if isinstance(altimeter_height, float) else None)

        # Latitude / Longitude
        engr_data.append(round(latitude, 6) if isinstance(latitude, float) else None)   # Latitude
        engr_data.append(round(longitude, 6) if isinstance(longitude, float) else None)  # Longitude

        return engr_data