"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

import pickle
import lzma

filename = '/home/vandaq/vandaq/collector/submission/submit_HaleyCar_20250108_095052_PST_.sbm'

with lzma.open(filename,'rb') as file:
    data = pickle.load(file)

pass

