# Python Standard Libraries
import math
import logging
import unittest
from scipy import signal, interpolate
import pandas as pd
import numpy as np


def depth(type: str, pressure: float, latitude: float) -> float:
    """
    Method to calculate the depth
    :param type: fresh_water or salt_water
    :param pressure: pressure in decibars
    :param latitude: latitude in degrees
    :return: depth in meters
    """
    if type == "fresh water":
        d = pressure * 1.019716

    else:
        x = (math.sin(latitude / 57.29578))**2
        gr = 9.780318 * (1.0 + (5.2788e-3 + 2.36e-5 * x) * x) + 1.092e-6 * pressure
        d = (((-1.82e-15 * pressure + 2.279e-10) * pressure - 2.2512e-5) * pressure + 9.72659) * pressure
        if gr:
            d /= gr

    return d


def pressure(f: float, M: float, B: float, pt_comp: float,
             c1: float, c2: float, c3: float,
             t1: float, t2: float, t3: float, t4: float, t5: float,
             d1: float, d2: float, slope: float, offset: float) -> float:
    """
    Method to determine the pressure from the pressure frequency and c, d, and t coefficients
    :param f: sensor frequency in Hz
    :param M:
    :param B:
    :param pt_comp:
    :param c1: c1 coefficient
    :param c2: c2 coefficient
    :param c3: c3 coefficient
    :param t1: t1 coefficient
    :param t2: t2 coefficient
    :param t3: t3 coefficient
    :param t4: t4 coefficient
    :param t5: t5 coefficient
    :param d1: d1 coefficient
    :param d2: d2 coefficient
    :param slope: slope
    :param offset: offset
    :return: pressure in decibars
    """
    try:
        td = M * pt_comp + B
        c = c1 + c2 * td + c3 * td**2
        d = d1 + d2 * td
        tX = t1 + t2 * td + t3 * td**2 + t4 * td**3 + t5 * td**4
        t0 = tX * 1.0e-06
        w = 1 - t0**2 * f ** 2

        p_decibar = slope * (0.6894759 * (c * w * (1 - d * w) - 14.7)) + offset
        p_psi = p_decibar * 1.450377

        return p_decibar
    except Exception as ex:
        logging.error(f"Error calculating pressure: {ex}")
        return None


def temperature(f: float, g: float, h: float, i: float, j: float, f0: float) -> float:
    """
    Method to derive the temperature
    :param f: Temperature frequency in Hz
    :param g: g coefficient
    :param h: h coefficient
    :param i: i coefficient
    :param j: j coefficient
    :param f0:
    :return:
    """
    try:
        if f == 0:
            parameters = f"f={f}, g={g}, h={h}, i={i}, j={j}, f0={f0}"
            logging.error(f"Error calculating temperature, frequency is 0: {parameters}")
            return None
        return 1 / (g + h * math.log(f0 / f) + i * (math.log(f0 / f)) ** 2 + j * (math.log(f0 / f)) ** 3) - 273.15
    except Exception as ex:
        logging.error(f"Error calculating temperature: {ex}")
        return None


def conductivity(f: float, g: float, h: float, i: float, j: float,
                 cpcor: float, ctcor: float,
                 T: float, P: float) -> float:
    """
    Function to calculate the conductivity
    :param f: Conductivity frequency in Hz
    :param g: g coefficient
    :param h: h coefficient
    :param i: i coefficient
    :param j: j coefficient
    :param cpcor: bulk compressibility of the borosilicate cell
    :param ctcor: thermal coefficient of expansion
    :param T: temperature, degrees celsius
    :param P: pressure, decibars
    :return: conductivity
    """
    try:
        f = f / 1000    # Convert to kHz

        return (g + h * f ** 2 + i * f ** 3 + j * f ** 4) / (10 * (1 + ctcor * T + cpcor * P))
    except Exception as ex:
        logging.error(f"Error calculating conductivity: {ex}")
        return None


def salinity(C: float, T: float, P: float) -> float:
    """
    Method to calculate the practical salinity
    :param C: conductivity 
    :param T: temperature 
    :param P: pressure
    :return: 
    """
    try:

        A1 = 2.070e-5
        A2 = -6.370e-10
        A3 = 3.989e-15
        B1 = 3.426e-2
        B2 = 4.464e-4
        B3 = 4.215e-1
        B4 = -3.107e-3
        C0 = 6.766097e-1
        C1 = 2.00564e-2
        C2 = 1.104259e-4
        C3 = -6.9698e-7
        C4 = 1.0031e-9
        a = [0.0080, -0.1692, 25.3851, 14.0941, -7.0261, 2.7081]
        b = [0.0005, -0.0056, -0.0066, -0.0375, 0.0636, -0.0144]

        if C <= 0.0:
            result = 0.0
        else:
            C *= 10.0
            R = C / 42.914
            val = 1 + B1 * T + B2 * T**2 + B3 * R + B4 * R * T
            if val:
                RP = 1 + (P * (A1 + P * (A2 + P * A3))) / val
            val = RP * (C0 + (T * (C1 + T * (C2 + T * (C3 + T * C4)))))
            if val:
                RT = R / val
            if RT <= 0.0:
                RT = 0.000001
            sum1 = sum2 = 0.0
            for i in range(6):
                temp = RT**(float(i)/2.0)
                sum1 += a[i] * temp
                sum2 += b[i] * temp
            val = 1.0 + 0.0162 * (T - 15.0)
            if val:
                result = sum1 + sum2 * (T - 15.0) / val
            else:
                result = -99.0

        return result

    except Exception as ex:
        logging.error(f"Error calculating salinity: {ex}")
        return None


def sound_velocity_chen_and_millero(s: float, t: float, p: float) -> float:
    """
    Method to calculate the sound velocity using the Chen & Millero method
    :param s: salinity
    :param t: temperature (deg C)
    :param p: pressure (decibars)
    :return:
    """
    try:
        p = p / 10.0    # Convert from decibars to bars
        if s < 0.0:
            s = 0.0
        sr = math.sqrt(s)
        d = 1.727e-3 - 7.9836e-6 * p
        b1 = 7.3637e-5 + 1.7945e-7 * t
        b0 = -1.922e-2 - 4.42e-5 * t
        b = b0 + b1 * p
        a3 = (-3.389e-13 * t + 6.649e-12) * t + 1.100e-10
        a2 = ((7.988e-12 * t - 1.6002e-10) * t + 9.1041e-9) * t - 3.9064e-7
        a1 = (((-2.0122e-10 * t + 1.0507e-8) * t - 6.4885e-8) * t - 1.2580e-5) * t + 9.4742e-5
        a0 = (((-3.21e-8 * t + 2.006e-6) * t + 7.164e-5) * t - 1.262e-2) * t + 1.389
        a = ((a3 * p + a2) * p + a1) * p + a0
        c3 = (-2.3643e-12 * t + 3.8504e-10) * t - 9.7729e-9
        c2 = (((1.0405e-12 * t - 2.5335e-10) * t + 2.5974e-8) * t - 1.7107e-6) * t + 3.1260e-5
        c1 = (((-6.1185e-10 * t + 1.3621e-7) * t - 8.1788e-6) * t + 6.8982e-4) * t + 0.153563
        c0 = ((((3.1464e-9 * t - 1.47800e-6) * t + 3.3420e-4) * t - 5.80852e-2) * t + 5.03711) * t + 1402.388
        c = ((c3 * p + c2) * p + c1) * p + c0
        sv = c + (a + b * sr + d * s) * s
        return sv
    except Exception as ex:
        logging.error(f"Error calculating chen millero sound velocity: {ex}")
        return None


def sound_velocity_delgrosso(s: float, t: float, p: float) -> float:
    """
    Method to calculate the sound velocity using the Delgrosso, 1974 method
    :param s: salinity
    :param t: temperature (deg C)
    :param p: pressure (decibars)
    :return:
    """
    try:
        c000 = 1402.392
        p = p / 9.80665     # convert pressure from decibars to KG / CM**2
        dct = (0.501109398873e1 - (0.550946843172e-1 - 0.22153596924e-3 * t) * t) * t
        dcs = (0.132952290781e1 + 0.128955756844e-3 * s) * s
        dcp = (0.156059257041e0 + (0.244998688441e-4 - 0.83392332513e-8 * p) * p) * p
        dcstp = -0.127562783426e-1 * t * s + 0.635191613389e-2 * t * p + 0.265484716608e-7 * t * t * \
            p * p - 0.159349479045e-5 * t * p * p + 0.522116437235e-9 * t * p * p * p - 0.438031096213e-6 * t * \
            t * t * p - 0.161674495909e-8 * s * s * p * p + 0.968403156410e-4 * t * t * s + 0.485639620015e-5 * \
            t * s * s * p - 0.340597039004e-3 * t * s * p
        sv = c000 + dct + dcs + dcp + dcstp
        return sv
    except Exception as ex:
        logging.error(f"Error calculating delgrosso sound velocity: {ex}")
        return None


def sound_velocity_wilson(s: float, t: float, p: float) -> float:
    """
    Method to calculate the sound velocity using the Wilson, 1960 method
    :param s: salinity
    :param t: temperature (deg C)
    :param p: pressure (decibars)
    :return: sound velocity
    """
    try:
        pr = 0.1019716 * (p + 10.1325)
        sd = s - 35.0
        a = (((7.9851e-6 * t - 2.6045e-4) * t - 4.4532e-2) * t + 4.5721) * t + 1449.14
        sv = (7.7711e-7 * t - 1.1244e-2) * t + 1.39799
        v0 = (1.69202e-3 * sd + sv) * sd + a
        a = ((4.5283e-8 * t + 7.4812e-6) * t - 1.8607e-4) * t + 0.16072
        sv = (1.579e-9 * t + 3.158e-8) * t + 7.7016e-5
        v1 = sv * sd + a
        a = (1.8563e-9 * t - 2.5294e-7) * t + 1.0268e-5
        sv = -1.2943e-7 * sd + a
        a = -1.9646e-10 * t + 3.5216e-9
        sv = (((-3.3603e-12 * pr + a) * pr + sv) * pr + v1) * pr + v0
        return sv
    except Exception as ex:
        logging.error(f"Error calculating wilson sound velocity: {ex}")
        return None


def oxygen(temperature: float, pressure: float, salinity: float, voltage: float,
           Soc: float, VOffset: float, A: float, B: float, C: float,
           E: float, tau20: float, D1: float, D2: float,
           H1: float, H2: float, H3: float,
           previous_voltage: float) -> float:
    """
    Method for calculating the Dissolved Oyxgen using the Seabird equation for
    the SBE 43 as found the Seabird Application Note 64, p. 4, here:
        http://www.seabird.com/document/an64-sbe-43-dissolved-oxygen-sensor-background-information-deployment-recommendations

    """
    try:
        tau = tau20 * math.exp(D1 * pressure + D2 * (temperature - 20))
        dvdt = voltage - previous_voltage if previous_voltage else 0
        oxsol = oxygen_solubility(salinity=salinity, temperature=temperature)
        K = temperature + 273.15

        # Equation from Seabird Application Note 64-2, June 2012, p. 1
        oxygen = (Soc * (voltage + VOffset + tau * dvdt)) * \
            (1.0 + A*temperature + B*temperature**2 + C*temperature**3) * \
            oxsol * math.exp(E * pressure / K)

        # Equation below from SBE 43 Calibration worksheet
        # oxygen = Soc * (voltage + VOffset) * \
        #          (1.0 + A*temperature + B*temperature**2 + C*temperature**3) *\
        #          oxsol * math.exp( E * pressure / K)

        return oxygen

    except Exception as ex:
        logging.error(f"Error calculating oxygen: {ex}")
        return None


def oxygen_solubility(salinity: float, temperature: float) -> float:
    """
    Method for calculating the Oxygen Solubility per Garcia & Gordon, as discussed
    in the SBE 43 Seabird Application Note 64, p. 8, here:
        http://www.seabird.com/document/an64-sbe-43-dissolved-oxygen-sensor-background-information-deployment-recommendations
    """
    try:
        # Define constants
        A0 = 2.00907
        A1 = 3.22014
        A2 = 4.0501
        A3 = 4.94457
        A4 = -0.256847
        A5 = 3.88767
        B0 = -0.00624523
        B1 = -0.00737614
        B2 = -0.010341
        B3 = -0.00817083
        C0 = -0.000000488682

        Ts = math.log((298.15 - temperature) / (273.15 + temperature))
        return math.exp(A0 + A1*Ts + A2*Ts**2 + A3*Ts**3 + A4*Ts**4 + A5*Ts**5 +
                        salinity * (B0 + B1*Ts + B2*Ts**2 + B3*Ts**3) + C0*salinity**2)

    except Exception as ex:
        logging.error(f"Error calculating oxygen solubility: {ex}")
        return None


def fluorescence(voltage: float, dark_output: float, scale_factor: float) -> float:
    """
    Method to calculate the fluorescence using the equation as found in Seabird Application Note 62:
        http://www.seabird.com/document/an62-calculating-calibration-coefficients-eco-fl-fluorometer-eco-ntu-turbidity-meter-and
    """
    try:
        return (voltage - dark_output) * scale_factor
    except Exception as ex:
        logging.error(f"Error calculating fluorescence: {ex}")
        return None


def turbidity(voltage: float, dark_output: float, scale_factor: float) -> float:
    """
    Method to calculate the turbidity using the equation as found in Seabird Application Note 62:
        http://www.seabird.com/document/an62-calculating-calibration-coefficients-eco-fl-fluorometer-eco-ntu-turbidity-meter-and
    """
    try:
        return (voltage - dark_output) * scale_factor
    except Exception as ex:
        logging.error(f"Error calculating turbidity: {ex}")
        return None


def altimeter_height(voltage: float, scale_factor: float, offset: float) -> float:
    """
    Method to calculate the altimeter height, per Seabird Application Note 95:
        http://www.seabird.com/document/an95-setting-altimeter-sea-bird-profiling-ctd
    """
    try:
        return (300 * voltage / scale_factor) + offset
    except Exception as ex:
        logging.error(f"Error calculating altimeter: {ex}")
        return None


def lat_or_lon_to_dd(input_str):
    """
    Convert a latitude or longitude string in the form of:
    ddd + " " + mm.mm + " " + h

    to decimal degrees

    :param input_str:
    :return:
    """
    try:
        [dd, mm, hem] = input_str.strip().split(" ")

    except Exception as ex:
        logging.info(f"error in converting latitude/longitude: {ex}")
        return None

    if dd is None or dd == "" or mm is None or mm == "" or hem.lower() not in ["n", "s", "w", "e"]:
        return None

    try:
        value = float(dd) + float(mm)/60
        if hem.lower() in ["w", "s"]:
            return -value
        return value
    except Exception as ex:
        return None


class TestEquations(unittest.TestCase):
    """
    Test equations
    """

    def setUp(self):
        pass

    def test_depth(self):

        type = "salt water"
        pressure = 2.015
        latitude = 35.8008333333
        d = depth(type=type, pressure=pressure, latitude=latitude)
        print(f"depth={d}")
        self.assertEqual(round(d, 3), 2.000)

    def test_depth_2012(self):

        type = "salt water"
        pressure = 33156.2578125
        latitude = 35.8008333333
        d = depth(type=type, pressure=pressure, latitude=latitude)
        print(f"depth={d}")
        output = 27.562
        self.assertEqual(round(d, 3), output)

    def test_pressure_2012(self):
        C1 = -2.848711e+004
        C2 = -9.167749e-001
        C3 = 8.255600e-003
        D1 = 3.636300e-002
        D2 = 0.000000e+000
        T1 = 3.018103e+001
        T2 = -7.837088e-004
        T3 = 4.077050e-006
        T4 = 2.292300e-009
        T5 = 0.000000e+000
        AD590M = 1.28598e-002
        AD590B = -8.62874e+000
        Slope = 1.00010121
        Offset = 1.39434
        pt_comp = 2045.9        # 2045.9 work
        frequency = 33156.2578125
        pres = pressure(f=frequency, M=AD590M, B=AD590B, pt_comp=pt_comp,
                        c1=C1, c2=C2, c3=C3, t1=T1, t2=T2, t3=T3, t4=T4, t5=T5,
                        d1=D1, d2=D2, slope=Slope, offset=Offset)
        output = 2.000
        self.assertEqual(round(pres, 3), output)

    def test_pressure(self):
        C1 = -2.848711e+004
        C2 = -9.167749e-001
        C3 = 8.255600e-003
        D1 = 3.636300e-002
        D2 = 0.000000e+000
        T1 = 3.018103e+001
        T2 = -7.837088e-004
        T3 = 4.077050e-006
        T4 = 2.292300e-009
        T5 = 0.000000e+000
        AD590M = 1.28598e-002
        AD590B = -8.62874e+000
        Slope = 1.00016
        Offset = 1.3265
        pt_comp = 1354.8 #2139.9  # TODO Fix - not sure what this should be
        pres = pressure(f= 33159.0, M=AD590M, B=AD590B, pt_comp=pt_comp,
                        c1=C1, c2=C2, c3=C3, t1=T1, t2=T2, t3=T3, t4=T4, t5=T5,
                        d1=D1, d2=D2, slope=Slope, offset=Offset)
        self.assertEqual(round(pres, 3), 12.998)

    def test_conductivity(self):
        self.c = dict()
        self.c["F_c"] = 6728.17578125
        self.c["G"] = -10.2031661
        self.c["H"] = 1.25585159
        self.c["I"] = -0.00176544102
        self.c["J"] = 0.000179338527
        self.c["delta"] = 3.25e-06
        self.c["epsilon"] = -9.57e-08
        self.c["temperature"] = 20.492843082230024
        self.c["pressure"] = 13.0592236857729
        cond = conductivity(f=self.c["F_c"], g=self.c["G"], h=self.c["H"], i=self.c["I"], j=self.c["J"],
                            T=self.c["temperature"], P=self.c["pressure"])
        self.assertEqual(cond, 4.647392355780951)

    def test_conductivity_worksheet(self):
        f = 5.63159e03
        g = -1.02100013e+001
        h = 1.25794268e+000
        i = -2.29686787e-003
        j = 2.19007441e-004
        ctcor = 3.2500e-006
        cpcor = -9.5700e-008
        t = 1.000000
        p = 1.000000
        cond = conductivity(f=f, g=g, h=h, i=i, j=j, cpcor=cpcor, ctcor=ctcor, T=t, P=p)
        answer = 2.94953
        self.assertEqual(round(cond, 7), answer)

    def test_salinity_worksheet(self):
        f = 5.63159e03
        g = -1.02100013e+001
        h = 1.25794268e+000
        i = -2.29686787e-003
        j = 2.19007441e-004
        ctcor = 3.2500e-006
        cpcor = -9.5700e-008
        c = 2.94953
        t = 1.000000
        p = 1.000000
        cond = salinity(C=c, T=t, P=p)
        answer = 34.4747
        self.assertEqual(round(cond, 4), answer)

    def test_oxygen_worksheet(self):
        # Calibration Coefficients
        Soc = 0.5777
        Voffset = -0.5282
        Tau20 = 1.79
        A = -3.7388e-003
        B = 1.5155e-004
        C = -2.6903e-006
        E = 0.036
        D1 = 1.92634e-4
        D2 = -4.64803e-2
        H1 = -3.300000e-2
        H2 = 5.00000e+3
        H3 = 1.45000e+3

        # Measured Values
        t = 30.00    # Temperature
        p = 0       # Pressure
        s = 0.00    # Salinity
        v = 1.928   # Oxygen Sensor Voltage
        answer = 4.07

        calculated_value = oxygen(temperature=t, pressure=p, salinity=s,
                         voltage=v, Soc=Soc, VOffset=Voffset,
                         A=A, B=B, C=C, E=E,
                         tau20=Tau20, D1=D1, D2=D2,
                         H1=H1, H2=H2, H3=H3, previous_voltage=0)
        self.assertEqual(round(calculated_value, 2), answer)

    def test_oxygen_2012(self):
        # Calibration Coefficients
        Soc = 5.6593e-001
        Voffset = -0.5250
        Tau20 = 2.0000
        A = -2.6845e-003
        B = 6.6602e-005
        C = -1.2035e-006
        E = 3.6000e-002
        D1 = 1.92634e-004
        D2 = -4.64803e-002
        H1 = -3.3000e-002
        H2 = 5.0000e+003
        H3 = 1.4500e+003

        # Measured Values
        t = 11.2860    # Temperature
        p = 2.015       # Pressure
        s = 33.8477    # Salinity
        v = 1.928   # Oxygen Sensor Voltage
        answer = 4.07

        calculated_value = oxygen(temperature=t, pressure=p, salinity=s,
                         voltage=v, Soc=Soc, VOffset=Voffset,
                         A=A, B=B, C=C, E=E,
                         tau20=Tau20, D1=D1, D2=D2,
                         H1=H1, H2=H2, H3=H3, previous_voltage=0)
        self.assertEqual(round(calculated_value, 2), answer)

    def test_fluorescence_worksheet(self):
        dark_output = 0.060
        scale_factor = 10
        voltage = 4.00
        answer = 39.4

        f = fluorescence(voltage=voltage, scale_factor=scale_factor, dark_output=dark_output)
        self.assertEqual(round(f,2), answer)

    def test_turbidity_worksheet(self):
        dark_output = 0.060     # V
        scale_factor = 5        # NTU/V
        voltage = 4.00
        answer = 19.7

        t = turbidity(voltage=voltage, scale_factor=scale_factor, dark_output=dark_output)

        self.assertEqual(round(t,2), answer)

    def test_temperature(self):
        pass

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()