import numpy as np
from numba import jit


@jit(nopython=True, cache=True)
def rgb2xyz(rgb):
    """Converts RGB pixel array to XYZ format."""
    rgb = rgb.astype(np.float64)
    for i in range(3):
        c = rgb[i]
        c = c / 255.0
        if c > 0.04045:
            c = ((c + 0.055) / 1.055) ** 2.4
        else:
            c = c / 12.92
        rgb[i] = c * 100
    xyz = np.zeros((3), dtype=np.float64)
    xyz[0] = rgb[0] * 0.4124 + rgb[1] * 0.3576 + rgb[2] * 0.1805
    xyz[1] = rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722
    xyz[2] = rgb[0] * 0.0193 + rgb[1] * 0.1192 + rgb[2] * 0.9505
    return xyz


@jit(nopython=True, cache=True)
def xyz2lab(xyz):
    """Converts XYZ pixel array to LAB format."""
    xyz[0] = xyz[0] / 95.047
    xyz[1] = xyz[1] / 100.00
    xyz[2] = xyz[2] / 108.883
    for i in range(3):
        if xyz[i] > 0.008856:
            xyz[i] = xyz[i] ** (1.0 / 3.0)
        else:
            xyz[i] = (7.787 * xyz[i]) + (16.0 / 116.0)
    lab = np.zeros((3), dtype=np.float64)
    lab[0] = (116.0 * xyz[1]) - 16.0
    lab[1] = 500.0 * (xyz[0] - xyz[1])
    lab[2] = 200.0 * (xyz[1] - xyz[2])
    return lab


@jit(nopython=True, cache=True)
def rgb2lab(rgb):
    """Convert RGB pixel array into LAB format."""
    return xyz2lab(rgb2xyz(rgb))


# from https://github.com/nschloe/colorio/blob/main/src/colorio/diff/_ciede2000.py
@jit(nopython=True, cache=True)
def ciede2000(
    lab1, lab2, k_L: float = 1.0, k_C: float = 1.0, k_H: float = 1.0
) -> np.ndarray:
    """Return CIEDE2000 comparison results of two LAB formatted colors."""
    lab1 = np.asarray(lab1)
    lab2 = np.asarray(lab2)

    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = np.sqrt(a1**2 + b1**2)
    C2 = np.sqrt(a2**2 + b2**2)
    C_mean = (C1 + C2) / 2

    G = 0.5 * (1 - np.sqrt(C_mean**7 / (C_mean**7 + 25**7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2

    C1p = np.sqrt(a1p**2 + b1**2)
    C2p = np.sqrt(a2p**2 + b2**2)

    # 0 <= h1p, h2p <= 360
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    # -360 <= hp_diff <= 360
    hp_diff = h2p - h1p
    # dhp is the circular distance between the angles h1p and h2p in degrees
    # make sure dhp is in the (-180, 180) range
    dhp = ((hp_diff + 180) % 360) - 180

    dLp = L2 - L1
    dCp = C2p - C1p
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))

    Lp_mean = (L1 + L2) / 2
    Cp_mean = (C1p + C2p) / 2
    hp_mean = ((dhp / 2) + h1p) % 360

    T = (
        1.0
        - 0.17 * np.cos(np.radians(hp_mean - 30))
        + 0.24 * np.cos(np.radians(2 * hp_mean))
        + 0.32 * np.cos(np.radians(3 * hp_mean + 6))
        - 0.20 * np.cos(np.radians(4 * hp_mean - 63))
    )
    dtheta = 30 * np.exp(-(((hp_mean - 275) / 25) ** 2))

    R_C = 2 * np.sqrt(Cp_mean**7 / (Cp_mean**7 + 25**7))
    S_L = 1 + 0.015 * (Lp_mean - 50) ** 2 / np.sqrt(20 + (Lp_mean - 50) ** 2)
    S_C = 1 + 0.045 * Cp_mean
    S_H = 1 + 0.015 * Cp_mean * T
    R_T = -np.sin(np.radians(2 * dtheta)) * R_C

    dE00 = np.sqrt(
        (dLp / k_L / S_L) ** 2
        + (dCp / k_C / S_C) ** 2
        + (dHp / k_H / S_H) ** 2
        + R_T * (dCp / k_C / S_C) * (dHp / k_H / S_H)
    )
    return dE00
