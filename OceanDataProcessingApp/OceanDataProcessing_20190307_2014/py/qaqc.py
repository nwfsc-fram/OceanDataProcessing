# Python Standard Libraries
import logging
import math
from scipy import signal, interpolate
import pandas as pd
import numpy as np

from py.seawater import sw_c3515, sw_salt, sw_cndr, sw_prandtl


def butterworth_filter(cutoff_per, samp_per):

    """
    Create a lowpass butterworth filter
    :param cutoff_per:
    :param samp_per: pandas dataframe containing the dt, i.e. the time difference
    :return:
    """
    if samp_per == 0:
        print(f"Error in getting the butterworth filter, samp_per = 0")
        return False, False

    order = 4

    nyquist_freq = 1 / (2 * float(samp_per))
    cutoff_freq = (1 / cutoff_per) / nyquist_freq

    # logging.info(f"nyquist={nyquist_freq}, samp_per={samp_per}, cutoff_freq={cutoff_freq}")

    b, a = signal.butter(N=order, Wn=cutoff_freq)

    return b, a


def set_downcast(df):
    """
    Method to specify whether the rows in a dataframe are part of the downcast or upcast.

    The dataframe must contain a column named:  Depth (m)
    :param df:
    :return:
    """
    if "Depth (m)" not in list(df.columns.values):
        return None

    # Check that the depth doesn't change too quickly between subsequent samples/rows
    # as those represent outlier values
    max_depth_change = 100      # in meters, between subsequent scans
    df['Prior Depth'] = df['Depth (m)'].shift(1)
    df['delta_depth'] = df['Depth (m)'] - df['Prior Depth']
    valid_depth_mask = (-max_depth_change < df['delta_depth']) & (df['delta_depth'] < max_depth_change)
    df_masked = df[valid_depth_mask]

    # Mask for the deepest values, having already discarded the extreme outliers
    mask = df_masked["Depth (m)"] == df_masked["Depth (m)"].max()
    values = df_masked.loc[mask].index.values
    # values = df.loc[mask].index.values
    # logging.info(f"values = {values}")
    if len(values) > 0:
        deepest_idx = values[-1]
        df.loc[:, "is_downcast"] = 0
        df.loc[df.loc[:, "is_downcast"].iloc[0:deepest_idx + 1].index, "is_downcast"] = 1
    else:
        df.loc[:, "is_downcast"] = 1

    df.drop(['Prior Depth', 'delta_depth'], axis=1, inplace=True)

    return df


def set_vertical_velocity(df=None, sampling_frequency=24):
    """
    Method to calculate the vertical velocity based on the changed in Pressure (decibar).
    This method assumes that we have the following columns in the dataframe:
        Date (YYYY-MM-DD)
        Time (HH:mm:ss)
        Pressure (decibar)

    :param df:
    :return:
    """
    if "Date (YYYY-MM-DD)" not in list(df.columns.values) or \
        "Time (HH:mm:ss)" not in list(df.columns.values) or \
        "Pressure (decibar)" not in list(df.columns.values):
        return df

    df["time"] = pd.DatetimeIndex(pd.to_datetime(df["Date (YYYY-MM-DD)"] + " " +
                                                 df["Time (HH:mm:ss)"],
                                                 format="%Y-%m-%d %H:%M:%S.%f")).astype(np.int64)
    size = len(df)
    df['dp'] = df['Pressure (decibar)'].rolling(window=3, center=True).apply(lambda x: x[2] - x[0])
    df.loc[0, 'dp'] = df.loc[1, 'dp']
    df.loc[size - 1, 'dp'] = df.loc[size - 2, 'dp']
    df['dt'] = (df['time'].shift() - df['time']).abs() / (10 ** 9)
    df['dpdt'] = df['dp'] / (2 * df['dt'])
    df.loc[0, 'dpdt'] = df.loc[1, 'dpdt']  # Fill in the first value
    df.loc[len(df) - 1:len(df) + 1, 'dpdt'] = df.loc[len(df) - 2, 'dpdt']  # Fill in the last two values

    return df


def low_pass_filter_pressure_velocity(df):
    """
    Method to perform low pass filtering on the pressure and vertical velocity
    :param df:
    :return:
    """
    if "dt" not in list(df.columns.values) or \
            "dpdt" not in list(df.columns.values) or \
            "Pressure (decibar)" not in list(df.columns.values):
        return df

    samp_per = df.iloc[1]['dt']  # units = seconds = 0.0625 seconds
    vertical_velocity_cutoff_per = 2  # units = seconds = 2 seconds

    [b, a] = butterworth_filter(cutoff_per=vertical_velocity_cutoff_per, samp_per=samp_per)
    df['dpdt_f'] = signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['dpdt'])))
    df['Pressure (decibar)'] = signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Pressure (decibar)'])))
    df['dPdt'] = df['dpdt_f'].copy()

    return df


def low_pass_filter_pressure(df=None, samp_per=None, cutoff_per=0.15):
    """
    Method to perform a low pass filter on the pressure only
    :param df: pandas DataFrame - should contain the Pressure (decibar) and dt columns
    :param samp_per: float - sample period, in seconds.  Typically:  CTD 911 = 1/24, UCTD = 1/16
    :param cutoff_per: float - time constant used for the filtering
    :return:
    """
    if "Pressure (decibar)" not in list(df.columns.values):
        return df

    if samp_per is None:
        if "dt" in list(df.columns.values):
            samp_per = df.iloc[1]['dt']  # units = seconds.   CTD = 1/24 = 0.0416667, UCTD = 1/16 = 0.0625 seconds
        else:
            return df

    [b, a] = butterworth_filter(cutoff_per=cutoff_per, samp_per=samp_per)
    df['Pressure (decibar)'] = signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Pressure (decibar)'])))

    return df


def low_pass_filter_temperature_conductivity(df=None, sampling_frequency=16):
    """
    Method to perform a low pass filter on the temperature and conductivity
    :param df:
    :return:
    """
    if "dt" not in list(df.columns.values) or \
            'Temperature (degC)' not in list(df.columns.values) or \
            'Conductivity (S_per_m)' not in list(df.columns.values):
        return df

    samp_per = df.iloc[1]['dt']  # units = seconds = 0.0625 seconds
    ct_filter_cutoff_per = 4 * (1/sampling_frequency)  # units = seconds, 0.25 seconds
    [b, a] = butterworth_filter(cutoff_per=ct_filter_cutoff_per, samp_per=samp_per)
    df['Temperature (degC)'] = \
        signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Temperature (degC)'])))
    df['Conductivity (S_per_m)'] = \
        signal.filtfilt(b=b, a=a, x=np.ravel(df.as_matrix(columns=['Conductivity (S_per_m)'])))

    return df


def calculate_temp_lag(df=None):
    """
    Calculate temperature lag value as a function of filtered vertical velocity
    :param df:
    :return:
    """
    if "dPdt" not in list(df.columns.values) or \
        "Temperature (degC)" not in list(df.columns.values):
        return df

    lag = [-0.810183190037050, -0.190621249755835, 0.126805428457073, 0.458221237250753, 0.715608325448966,
           0.886935565443651, 1.00134464049720, 1.08154805953019, 1.13757483933325, 1.15449025724993,
           1.21413817218518, 1.24662487047467, 1.27898261283749, 1.29319799601310]
    vvbin = [0.5 + 0.25 * x for x in range(1, 15)]
    f = interpolate.interp1d(x=vvbin, y=lag, kind='linear', fill_value='extrapolate')
    lagval = f(df['dPdt'])
    scan = range(1, len(df) + 1)
    scan_interp = scan + lagval
    f2 = interpolate.interp1d(x=scan, y=df["Temperature (degC)"], fill_value='extrapolate')
    df.loc[:, "Temperature (degC)"] = f2(scan_interp)

    return df


def correct_viscious_heating(df=None):
    """
    Method to correct for viscous heating using Seabird empirical equation
    :param df:
    :return:
    """
    if "Conductivity (S_per_m)" not in list(df.columns.values) or \
        "Pressure (decibar)" not in list(df.columns.values) or \
        "Temperature (degC)" not in list(df.columns.values):
        return df

    c3515 = sw_c3515() / 10  # Reference conductivity value
    salt = sw_salt(df["Conductivity (S_per_m)"] / c3515, df["Temperature (degC)"], df["Pressure (decibar)"])
    prandtl_number = sw_prandtl(T=df["Temperature (degC)"], S=salt)
    dT = 0.8e-04 * (prandtl_number ** 0.5) * (df['dPdt'] ** 2)
    df['Temperature (degC)'] = df["Temperature (degC)"] - dT

    return df


def calculate_uctd_conductivity_cell_velocity(dpdt):
    """
    Method to calculate the velocity in the conductivity cell
    :param dpdt: dP/dt (decibar/s) = freestream velocity (m/s)
    :return:
    """
    nu = 1.36e-06  # kinematic viscosity of water (m^2/s)
    dl = 0.1725  # distance between the UCTD inlet and output ports (m)
    a = 2e-03  # radius of conductivity cell tube (m)

    cell_velocity = (-8 * nu * dl + (((8 * nu * dl) ** 2) + (a ** 4) * (dpdt ** 2)) ** 0.5) / (a ** 2)

    return cell_velocity


def calculate_thermal_mass_coefficients(cell_velocity):
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


def compute_gamma(C, T, P):
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

    gamma = (C1 - C2) / (2 * delta_T)

    return gamma


def correct_thermal_mass(C, T, P, alpha, tau):
    """
    Method to calculate the thermal mass correction
    :param C:
    :param T:
    :param P:
    :param alpha:
    :param tau:
    :return:
    """
    if isinstance(alpha, float):
        alpha = pd.Series(alpha, index=range(len(C)), dtype='float')
    if isinstance(tau, float):
        tau = pd.Series(tau, index=range(len(C)), dtype='float')

    scan_rate = 16
    beta = 1 / tau
    dt = 1 / scan_rate
    a = 2 * alpha / (2 + beta * dt)
    b = 1 - (2 * a / alpha)

    # Compute conductivity sensitivity to Temperature using mean values
    gamma = compute_gamma(C=C, T=T, P=P)

    C_corr = pd.Series(0, index=range(len(C)), dtype='float')
    for i in range(1, len(C)):
        C_corr[i] = -b[i] * C_corr[i-1] + a[i] * gamma[i] * (T[i] - T[i-1])
        if math.isnan(C_corr[i]):
            C_corr[i] = C_corr[i-1]

    C_corr = C_corr + C

    return C_corr


def correct_loop_edit(df=None, window_time=30, sampling_frequency=24, threshold_velocity=0.2):
    """
    Perform loop edit corrections.  Seasoft Data Processing 7.26.8.0.pdf, p. 103
    :param df: DataFrame
    :param window_time: int - seconds
    :param sampling_frequency: int
    :return:
    """
    if "dPdt" not in list(df.columns.values) and \
            "dpdt" not in list(df.columns.values):
        return df

    if "dPdt" not in list(df.columns.values):
        df["dPdt"] = df["dpdt"]
    if "dPdt invalid" not in list(df.columns.values):
        df["dPdt invalid"] = False

    window = window_time * sampling_frequency    # min x sec/min x sampling frequency
    df['dPdt_mean'] = df["dPdt"].rolling(window=window, center=True).mean()
    df["dPdt invalid"] = df.apply(lambda x: True if x["dPdt"] < (1-threshold_velocity) * x["dPdt_mean"] else False,
                                  axis=1)

    return df


def bin_depths(df=None, bin_size=1, average=True):
    """
    Method to bin the output by depth size provide by bin_size
    :param output_file: str - full path of the output file that will be created from this process
    :param df: pandas dataframe - the dataframe  that will be binned
    :param bin_size: depth size bin in meters
    :param average: True/False - average within the bins or not
    :return:
    """
    if not isinstance(df, pd.DataFrame):
        logging.error(f"The df variable is not a pandas DataFrame, please try again: {ex}")
        return None

    if isinstance(df, pd.DataFrame) and df.empty:
        logging.error(f"The dataframe is empty, skipping binning")
        return

    if "Depth (m)" not in list(df.columns.values):
        logging.error(f"The Depth (m) column is not present in the dataframe for binning")
        return None

    source_col_name = f"Depth (m)"
    binned_col_name = f"Depth Binned ({bin_size}m)"
    max_depth = math.floor(df['Depth (m)'].max())
    bin_size = int(bin_size)
    bins = [x for x in range(0, max_depth+2, bin_size)]

    try:
        # Remove rows that contain invalid data
        # TODO Todd Hay - Add Salinity invalid potentially and what about cascading invalid data, how to handle?
        if "dPdt invalid" in list(df.columns.values):
            mask = ((~df["Temperature (degC) invalid"]) &
                    (~df["Conductivity (S_per_m) invalid"]) &
                    (~df["Pressure (decibar) invalid"]) &
                    (~df["dPdt invalid"])
                    )
        else:
            mask = ((~df["Temperature (degC) invalid"]) &
                    (~df["Conductivity (S_per_m) invalid"]) &
                    (~df["Pressure (decibar) invalid"]))

        df = df[mask]

        # Remove invalid columns
        cols = [x for x in df.columns.values if "invalid" not in x]
        df = df.loc[:, cols]

        # Get the columns that will be averaged
        avg_cols = [x for x in df.columns.values if binned_col_name not in x]
        avg_cols.append("dt")

        # Create a datetime in Epoch format (nanoseconds since Jan 1st, 1970) - used later for datetime averaging
        if "Time (HH:mm:ss)" in list(df.columns.values):
            df.loc[:, "dt"] = pd.DatetimeIndex(pd.to_datetime(df["Date (YYYY-MM-DD)"] + " " +
                                                          df["Time (HH:mm:ss)"],
                                                          format="%Y-%m-%d %H:%M:%S")).astype(np.int64)
        else:
            df.loc[:, "dt"] = pd.DatetimeIndex(pd.to_datetime(df["Date (YYYY-MM-DD)"],
                                                              format="%Y-%m-%d")).astype(np.int64)

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
        if "Time (HH:mm:ss)" in list(df.columns.values):
            df_output.loc[:, "Time (HH:mm:ss)"] = df_output.loc[:, "dt"].dt.strftime("%H:%M:%S")

        # Drop extraneous columns
        cols_to_drop = list()
        for col in ["Scan #", "dt", "scan#"]:
            if col in list(df_output.columns.values):
                cols_to_drop.append(col)
        df_output.drop(cols_to_drop, axis=1, inplace=True)

        # Round the output columns to precision = 6
        df_output = df_output.round(6)

        df_output["is_downcast"] = df_output["is_downcast"].astype(int)

        return df_output

    except Exception as ex:
        logging.error(f"Error binning the data: {ex}")


if __name__ == '__main__':

    pass