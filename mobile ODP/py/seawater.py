"""
Seawater equations adapted from Ullman et al MATLAB code
"""
import math
import logging
import numpy as np
import pandas as pd

def sw_prandtl(T, S):
    """
    Method to calculate the Prandtl number [-] from the specific heat, viscosity, and thermal conductivity functions

    :param T: Temperaturer (degC)
    :param S: Salinity (g/kg) (reference-composition salinity)
    :return:
    """
    cp = sw_specific_heat(T, S)
    mu = sw_viscosity(T, S)
    k = sw_conductivity(T, S)
    Pr = cp * mu / k
    return Pr

def sw_specific_heat(T, S):
    """
    Calculate specific heat of seawater at 0.1 MPa given by
        D. T. Jamieson, J. S. Tudhope, R. Morris, and G. Cartwright,
              Physical properties of sea water solutions: heat capacity,
              Desalination, 7(1), 23-30, 1969.

    Validity:   0 < T < 180 degC;  0 < S < 180 g/kg

    :param T:
    :param S:
    :return:
    """
    T = 1.00024 * T     # Convert from T_90 to T_68
    S = S / 1.00472     # Convert fromr S to S_P

    A = 4206.8 - 6.6197 * S + 1.2288e-2 * (S ** 2)
    B = -1.1262 + 5.4178e-2 * S - 2.2719e-4 * (S ** 2)
    C = 1.2026e-2 - 5.3566e-4 * S + 1.8906e-6 * (S ** 2)
    D = 6.8777e-7 + 1.517e-6 * S - 4.4268e-9 * (S ** 2)
    cp = A + B * T + C * (T ** 2) + D * (T ** 3)

    return cp

def sw_viscosity(T, S):
    """
    Method to calculate the dynamic viscosity (kg/m s)
    :param T:
    :param S:
    :return:
    """
    S = S / 1000

    a1 = 1.5700386464e-01
    a2 = 6.4992620050e+01
    a3 = -9.1296496657e+01
    a4 = 4.2844324477e-05

    mu_w = a4 + 1/(a1*(T+a2)**2+a3)

    a5 = 1.5409136040e+00
    a6 = 1.9981117208e-02
    a7 = -9.5203865864e-05
    a8 = 7.9739318223e+00
    a9 = -7.5614568881e-02
    a10 = 4.7237011074e-04
    A = a5 + a6 * T + a7 * (T**2)
    B = a8 + a9 * T + a10* (T**2)
    mu = mu_w*(1 + A*S + B*(S**2))

    return mu

def sw_conductivity(T, S):
    """
    Method to calculate the thermal conducitivity (W/m K)
    :param T:
    :param S:
    :return:
    """
    T = 1.00024 * T     # Convert from T_90 to T_68
    S = S / 1.00472     # Convert from S to S_P

    k = 0.001 * (10 ** (np.log10(240 + 0.0002 * S) + 0.434 * (2.3 - (343.5 + 0.037 * S) / (T + 273.15)) * \
                ((1 - (T + 273.15) / (647.3 + 0.03 * S))) ** (1 / 3)))

    return k

def sw_salt(R, T, P):
    """
    Calculate salinity from conductivity ratio.  UNESCO 1983 polynomial
    :param R: panndas Series, Conductivity ratio
    :param T: pandas Series, Temperature (degC) (ITS-90)
    :param P: pandas Series, Pressure (decibar)
    :return: S: pandas Series, Salinity (psu)   (PSS-78)
    """
    rt = sw_salrt(T)
    Rp = sw_salrp(R, T, P)
    Rt = R / (Rp * rt)
    S = sw_sals(Rt, T)

    return S

def sw_salrt(T):
    """
    Method to calculat the conductivity ratio
    :param T: pandas Series - Temperature (degC)
    :return:  conductivity ratio (no units)
    """
    T68 = T * 1.00024

    c0 = 0.6766097
    c1 = 2.00564e-2
    c2 = 1.104259e-4
    c3 = -6.9698e-7
    c4 = 1.0031e-9

    rt = c0 + (c1 + (c2 + (c3 + c4 * T68) * T68) * T68) * T68

    return rt

def sw_salrp(R, T, P):
    """
    Method to calculate the conductivity ratio
    :param R: pandas Series - Conductivity ratio, R = C(S, T, P) / C(S, T, 0) used in calculating salinity
    :param T: pandas Series - Temperature (degC) (ITS-90)
    :param P: pandas Series - Pressure (decibar)
    :return: Rp:  Conductivity ratio
    """
    T68 = T * 1.00024

    d1 = 3.426e-2
    d2 = 4.464e-4
    d3 = 4.215e-1
    d4 = -3.107e-3

    e1 = 2.070e-5
    e2 = -6.370e-10
    e3 = 3.989e-15

    Rp = 1 + (P * (e1 + e2 * P + e3 * (P ** 2))) / \
         (1 + d1 * T68 + d2 * (T68 ** 2) + (d3 + d4 * T68) * R)

    return Rp

def sw_sals(Rt, T):
    """
    Method to calculate the salinity of sea water as a function of Rt and T, UNESCO 1983 polynomial
    :param Rt: pandas Series - C(S, T, 0) / C(35, T, 0)
    :param T: pandas Series - Temperature (degC) (ITS-90)
    :return:
    """
    del_T68 = T * 1.00024 - 15

    a0 =  0.0080
    a1 = -0.1692
    a2 = 25.3851
    a3 = 14.0941
    a4 = -7.0261
    a5 =  2.7081

    b0 =  0.0005
    b1 = -0.0056
    b2 = -0.0066
    b3 = -0.0375
    b4 =  0.0636
    b5 = -0.0144

    k = 0.0162

    Rtx = Rt ** 0.5
    del_S = (del_T68 / (1 + k * del_T68) ) * \
        ( b0 + (b1 + (b2+ (b3 + (b4 + b5 * Rtx) * Rtx) * Rtx) * Rtx) * Rtx)

    S = a0 + (a1 + (a2 + (a3 + (a4 + a5 * Rtx) * Rtx) * Rtx) * Rtx) * Rtx

    S = S + del_S

    return S

def sw_salds(Rtx, delT):
    """
    Method to calculate the Salinity differential dS/d(sqrt(Rt)) at constant T.
    UNESCO 1983 polynomial.
    :param R:
    :param T:
    :return:
    """
    a0 = 0.0080
    a1 = -0.1692
    a2 = 25.3851
    a3 = 14.0941
    a4 = -7.0261
    a5 = 2.7081

    b0 = 0.0005
    b1 = -0.0056
    b2 = -0.0066
    b3 = -0.0375
    b4 = 0.0636
    b5 = -0.0144

    k = 0.0162

    dS = a1 + (2*a2 + (3*a3 + (4*a4 + 5*a5*Rtx) * Rtx) * Rtx) * Rtx + \
         (delT / (1 + k * delT)) * \
         (b1 + (2*b2 + (3*b3 + (4*b4 + 5*b5*Rtx) * Rtx) * Rtx) * Rtx)

    return dS

def sw_c3515():
    """
    Returns the conductivity at S = 35 psu, T =1 5 C (ITPS 68) and P = 0 decibar
    :return:
    """
    return 42.914

def sw_cndr(S, T, P):
    """
    Method to calculate the conductivity ratio from S, T, P
    :param S:
    :param T:
    :param P:
    :return:
    """
    T68 = T * 1.00024

    Rx = pd.Series(index=range(len(S)), dtype='float')

    for i in range(len(S)):
        s_loop = S[i]
        t_loop = T[i]
        Rx_loop = (s_loop / 35.0) ** 0.5 if s_loop >= 0 else 0
        SInc = sw_sals(Rx_loop * Rx_loop, t_loop)
        iloop = 0
        end_loop = 0

        # if 167 <= i < 172:
        #     logging.info(f"OUTSIDE ::: {i} > s_loop = {s_loop}, SInc = {SInc}, Rx_loop = {Rx_loop}")

        dels = 10000
        previous_rx_loop = Rx_loop

        while not end_loop:

            if dels > 1.0e-10 and iloop < 100 and Rx_loop >= 0.0005:
                end_loop = False
            else:
                if Rx_loop < 0.0005:
                    Rx_loop = previous_rx_loop
                break
                end_loop = True

            previous_rx_loop = Rx_loop

            Rx_loop = Rx_loop + (s_loop - SInc) / sw_salds(Rx_loop, t_loop/1.00024 - 15)
            SInc = sw_sals(Rx_loop * Rx_loop, t_loop)
            iloop += 1
            dels = math.fabs(SInc - s_loop)

            # if i == 169 and iloop <= 10:
            #     logging.info(f"row={i} > iloop={iloop}, dels={dels:.5f}, Rx_loop={Rx_loop:.5f}, SInc = {SInc:.5f}, salds={sw_salds(Rx_loop, t_loop/1.00024 - 15):.5f}")

        Rx[i] = Rx_loop

    # logging.info(f"Rx =\n{Rx.loc[167:172]}")

    d1 = 3.426e-2
    d2 = 4.464e-4
    d3 = 4.215e-1
    d4 = -3.107e-3

    e1 = 2.070e-5
    e2 = -6.370e-10
    e3 = 3.989e-15

    A = (d3 + d4 * T68)
    B = 1 + d1 * T68 + d2 * (T68 ** 2)
    C = P * (e1 + e2 * P + e3 * (P ** 2))

    Rt = Rx * Rx
    rt = sw_salrt(T=T)
    # Rtrt = rt * Rt
    D = B - A * rt * Rt
    E = rt * Rt * A * (B + C)
    R = np.sqrt(np.abs(D ** 2 + 4*E)) - D
    R = 0.5 * R / A

    return R

def sw_dens(S, T, P):

    dens_P0 = sw_dens0(S, T)
    K = sw_seck(S, T, P)
    P = P / 10
    dens = dens_P0 / (1 - P / K)

    return dens

def sw_dens0(S, T):

    T68 = T * 1.00024

    b0 = 8.24493e-1
    b1 = -4.0899e-3
    b2 = 7.6438e-5
    b3 = -8.2467e-7
    b4 = 5.3875e-9

    c0 = -5.72466e-3
    c1 = +1.0227e-4
    c2 = -1.6546e-6

    d0 = 4.8314e-4
    dens = sw_smow(T) + (b0 + (b1 + (b2 + (b3 + b4 * T68) * T68) * T68) * T68) * S \
           + (c0 + (c1 + c2 * T68) * T68) * S * (S ** 0.5) + d0 * (S ** 2)

    return dens

def sw_seck(S, T, P):

    # Compute compression terms
    P = P / 10
    T68 = T * 1.00024

    h3 = -5.77905e-7
    h2 = 1.16092e-4
    h1 = 1.43713e-3
    h0 = 3.239908

    AW = h0 + (h1 + (h2 + h3 * T68) * T68) * T68

    k2 = 5.2787e-8
    k1 = -6.12293e-6
    k0 = 8.50935e-5

    BW = k0 + (k1 + k2 * T68) * T68

    e4 = -5.155288e-5
    e3 = 1.360477e-2
    e2 = -2.327105
    e1 = 148.4206
    e0 = 19652.21

    KW = e0 + (e1 + (e2 + (e3 + e4 * T68) * T68) * T68) * T68

    # SEA WATER TERMS OF SECANT BULK MODULUS AT ATMOS PRESSURE
    j0 = 1.91075e-4

    i2 = -1.6078e-6
    i1 = -1.0981e-5
    i0 = 2.2838e-3

    SR = S ** 0.5

    A = AW + (i0 + (i1 + i2 * T68) * T68 + j0 * SR) * S

    m2 = 9.1697e-10
    m1 = +2.0816e-8
    m0 = -9.9348e-7

    B = BW + (m0 + (m1 + m2 * T68) * T68) * S

    f3 = -6.1670e-5
    f2 = +1.09987e-2
    f1 = -0.603459
    f0 = +54.6746

    g2 = -5.3009e-4
    g1 = +1.6483e-2
    g0 = +7.944e-2

    K0 = KW + (f0 + (f1 + (f2 + f3 * T68) * T68) * T68 + (g0 + (g1 + g2 * T68) * T68) * SR) * S

    K = K0 + (A + B * P) * P

    return K

def sw_smow(T):

    a0 = 999.842594
    a1 = 6.793952e-2
    a2 = -9.095290e-3
    a3 = 1.001685e-4
    a4 = -1.120083e-6
    a5 = 6.536332e-9

    T68 = T * 1.00024
    dens = a0 + (a1 + (a2 + (a3 + (a4 + a5 * T68) * T68) * T68) * T68) * T68

    return dens

def sw_pden(S, T, P, PR):
    """
    Method to calculate the potential density
    :param S:
    :param T:
    :param P:
    :param PR:
    :return:
    """
    ptmp = sw_ptmp(S=S, T=T, P=P, PR=PR)
    pden = sw_dens(S=S, T=ptmp, P=PR)

    return pden

def sw_ptmp(S, T, P, PR):
    """
    Method to calculate the potential temperature
    :param S:
    :param T:
    :param P:
    :param PR:
    :return:
    """
    # theta1
    del_P = PR - P
    del_th = del_P * sw_adtg(S, T, P)
    th = T * 1.00024 + 0.5 * del_th
    q = del_th

    # theta2
    del_th = del_P * sw_adtg(S, th / 1.00024, P + 0.5 * del_P)
    th = th + (1 - 1 / math.sqrt(2)) * (del_th - q)
    q = (2 - math.sqrt(2)) * del_th + (-2 + 3 / math.sqrt(2)) * q

    # theta3
    del_th = del_P * sw_adtg(S, th / 1.00024, P + 0.5 * del_P)
    th = th + (1 + 1 / math.sqrt(2)) * (del_th - q)
    q = (2 + math.sqrt(2)) * del_th + (-2 - 3 / math.sqrt(2)) * q

    # theta4
    del_th = del_P * sw_adtg(S, th / 1.00024, P + del_P)
    PT = (th + (del_th - 2 * q) / 6) / 1.00024

    return PT

def sw_adtg(S, T, P):
    """
    Method to calculate the adiabatic temperature gradient
    :param S:
    :param T:
    :param P:
    :return:
    """
    T68 = 1.00024 * T

    a0 = 3.5803E-5
    a1 = +8.5258E-6
    a2 = -6.836E-8
    a3 = 6.6228E-10

    b0 = +1.8932E-6
    b1 = -4.2393E-8

    c0 = +1.8741E-8
    c1 = -6.7795E-10
    c2 = +8.733E-12
    c3 = -5.4481E-14

    d0 = -1.1351E-10
    d1 = 2.7759E-12

    e0 = -4.6206E-13
    e1 = +1.8676E-14
    e2 = -2.1687E-16

    adtg = a0 + ((a1 + (a2 + a3 * T68) * T68) * T68) \
        + (b0 + b1 * T68) * (S - 35) \
        + ((c0 + (c1 + (c2 + c3 * T68) * T68) * T68)
        + (d0 + d1 * T68) * (S - 35)) * P  \
        + (e0 + (e1 + e2 * T68) * T68) * P * P

    return adtg