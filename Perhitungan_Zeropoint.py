import math

# Data umum
mag_katalog = 10.72
flux_pengamatan = 525248  # ADU
F0 = 3.63e-9  # erg/s/cm²/Hz
wavelength = 550e-9  # meter
h = 6.626e-34  # Planck constant (J·s)
c = 3e8  # Speed of light (m/s)

# Teleskop dan CCD data
telescopes = {
    "GSO": {"aperture": 0.254},
    "Celestron C11": {"aperture": 0.28},
}

ccds = {
    "ZWO ASI 178MM": {"gain": 1.5, "quantum_efficiency": 0.75},
    "ZWO ASI 2600 MM Pro": {"gain": 1.0, "quantum_efficiency": 0.91},
    "QHY 174 GPS": {"gain": 2.0, "quantum_efficiency": 0.65},
}

# Hitung fluks katalog
flux_katalog = F0 * 10 ** (-0.4 * mag_katalog)

# Energi per foton
energy_per_photon = (h * c / wavelength) * 1e7  # erg

# Perhitungan zeropoint untuk setiap kombinasi
results = []
for telescope_name, telescope_data in telescopes.items():
    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2  # m²
    for ccd_name, ccd_data in ccds.items():
        gain = ccd_data["gain"]
        qe = ccd_data["quantum_efficiency"]

        # Fluks pengamatan dalam erg/s/cm²/Hz
        flux_pengamatan_erg = (flux_pengamatan * gain * energy_per_photon) / (qe * aperture_area)

        # Hitung zeropoint
        zeropoint = -2.5 * math.log10(flux_pengamatan_erg / flux_katalog)

        # Simpan hasil
        results.append((telescope_name, ccd_name, zeropoint))

# Tampilkan hasil
for telescope, ccd, zeropoint in results:
    print(f"Telescope: {telescope}, CCD: {ccd}, Zeropoint (filter V): {zeropoint:.2f}")