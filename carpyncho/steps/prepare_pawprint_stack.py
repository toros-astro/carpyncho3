# -*- coding: utf-8 -*-

# =============================================================================
# IMPORTS
# =============================================================================

import shutil
import tempfile
import os
import copy

import sh

import numpy as np

from corral import run

from astropy.io import fits

from .. import bin
from ..lib.context_managers import cd
from ..models import PawprintStack


# =============================================================================
# CONSTANTS
# =============================================================================

SOURCE_DTYPE = {
    "names": ['ra_h', 'ra_m', 'ra_s', 'dec_d', 'dec_m', 'dec_s'],
    "formats": [int, int, float, int, int, float]
}

PAWPRINT_DTYPE = {
    "names": [
        'ra_h', 'ra_m', 'ra_s', 'dec_d', 'dec_m', 'dec_s', 'x', 'y',
        'mag1', 'mag_err1', 'mag2', 'mag_err2',
        'mag3', 'mag_err3', 'mag4', 'mag_err4',
        'mag5', 'mag_err5', 'mag6', 'mag_err6', 'mag7', 'mag_err7',
        'chip_nro', 'stel_cls', 'elip', 'pos_ang', 'confidence',
    ],
    "formats": [
        int, int, float, int, int, float, float, float,
        float, float, float, float,
        float, float, float, float,
        float, float, float, float, float, float,
        int, int, float, float, float
    ]
}


# =============================================================================
# COMMANDS
# =============================================================================

vvv_flx2mag = sh.Command(bin.get("vvv_flx2mag"))


# =============================================================================
# STEPS
# =============================================================================

class PreparePawprintStack(run.Step):
    """Convert the pawprint into a numpy array
    ans also set the mjd and band metadata

    """

    model = PawprintStack
    conditions = [model.status == "raw"]
    groups = ["preprocess"]

    # =========================================================================
    # STEP SETUP & TEARDOWN
    # =========================================================================

    def setup(self):
        self.temp_directory = tempfile.mkdtemp(suffix="_carpyncho_ppstk")

    def teardown(self, *args, **kwargs):
        if not os.path.exists(self.temp_directory):
            shutil.rmtree(self.temp_directory)

    # =========================================================================
    # EXTRACT HEADER
    # =========================================================================

    def extract_headers(self, hdulist):
        mjd = hdulist[0].header["MJD-OBS"]
        band = hdulist[0].header["ESO INS FILT1 NAME"].strip()
        return band, mjd

    # =========================================================================
    # TO ARRAY
    # =========================================================================

    def load_fit(self, pawprint):
        to_cd = os.path.dirname(pawprint)
        basename = os.path.basename(pawprint)
        asciiname = os.path.splitext(basename)[0] + ".txt"
        asciipath = os.path.join(self.temp_directory, asciiname)

        # create the ascii table
        with cd(to_cd):
            vvv_flx2mag(basename, asciipath)

        # read ascii table
        odata = np.genfromtxt(asciipath, PAWPRINT_DTYPE)
        return odata

    def add_columns(self, odata, dtypes):
        """Add ra_deg and dec_deg columns to existing recarray

        """

        # calculate the ra and the dec columns
        radeg = 15 * (odata['ra_h'] +
                      odata['ra_m'] / 60.0 +
                      odata['ra_s'] / 3600.0)

        decdeg = np.sign(odata['dec_d']) * (np.abs(odata['dec_d']) +
                                            odata['dec_m'] / 60.0 +
                                            odata['dec_s'] / 3600.0)

        # create a new dtype to store the ra and dec as degrees
        dtype = copy.deepcopy(dtypes)
        dtype["names"].insert(0, "dec_deg")
        dtype["names"].insert(0, "ra_deg")
        dtype["formats"].insert(0, float)
        dtype["formats"].insert(0, float)

        # create an empty array and copy the values
        data = np.empty(len(odata), dtype=dtype)
        for name in data.dtype.names:
            if name == "ra_deg":
                data[name] = radeg
            elif name == "dec_deg":
                data[name] = decdeg
            else:
                data[name] = odata[name]
        return data

    def to_array(self, pwp_stk):
        original_array = self.load_fit(pwp_stk.raw_file_path)
        arr = self.add_columns(original_array, PAWPRINT_DTYPE)
        return arr

    # =========================================================================
    # STEP FUNCTIONS
    # =========================================================================

    def process(self, pwp):
        with fits.open(pwp.raw_file_path) as hdulist:
            pwp.band, pwp.mjd = self.extract_headers(hdulist)

        arr = self.to_array(pwp)
        pwp.store_npy_file(arr)

        yield pwp