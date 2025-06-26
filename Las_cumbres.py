from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import math
from fastapi.staticfiles import StaticFiles
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

# Data teleskop dan CCD
telescopes = {
    "GSO": {"aperture": 0.254, "pixel_scale": 0.57, "gain": 1.0, "read_noise": 3.0, "dark_current": 0.0},
    "Celestron C11": {"aperture": 0.28, "pixel_scale": 0.389, "gain": 1.0, "read_noise": 2.0, "dark_current": 0.0},
}

ccds = {
    "ZWO ASI 178MM": {"quantum_efficiency": 0.75, "read_noise": 3.0, "pixel_size": 2.4, "dark_current": 0.0},
    "ZWO ASI 2600 MM Pro": {"quantum_efficiency": 0.91, "read_noise": 1.5, "pixel_size": 3.76, "dark_current": 0.0022},
    "QHY 174 GPS": {"quantum_efficiency": 0.65, "read_noise": 2.0, "pixel_size": 5.86, "dark_current": 0.0},
}

# Kombinasi OTA dan CCD dengan zeropoint
combinations = {
    ("GSO", "ZWO ASI 178MM"): {"zeropoint": 25.12},
    ("GSO", "ZWO ASI 2600 MM Pro"): {"zeropoint": 25.45},
    ("GSO", "QHY 174 GPS"): {"zeropoint": 24.78},
    ("Celestron C11", "ZWO ASI 178MM"): {"zeropoint": 25.23},
    ("Celestron C11", "ZWO ASI 2600 MM Pro"): {"zeropoint": 25.56},
    ("Celestron C11", "QHY 174 GPS"): {"zeropoint": 24.89},
}

# Koefisien ekstingsi
k = {"U": 0.25, "B": 0.21, "V": 1.21, "R": 0.21, "I": 0.21, "Clear": 0.21}

# Fungsi untuk menghitung flux bintang
def calculate_flux(magnitude, zeropoint):
    return 10 ** (-0.4 * (magnitude - zeropoint))

# Fungsi untuk menghitung SNR
def calculate_snr(telescope, ccd, magnitude, exposure_time, fwhm, airmass, filter_name, sky_brightness):
    telescope_data = telescopes[telescope]
    ccd_data = ccds[ccd]
    zeropoint = combinations[(telescope, ccd)]["zeropoint"]

    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2
    pixel_scale = ccd_data["pixel_size"] / 1000  # Konversi dari micrometer ke mm
    read_noise = ccd_data["read_noise"]
    dark_current = ccd_data["dark_current"]
    quantum_efficiency = ccd_data["quantum_efficiency"]

    extinction = k[filter_name]
    extinction_correction = extinction * (airmass - 1)
    flux_star = calculate_flux(magnitude + extinction_correction, zeropoint) * aperture_area * quantum_efficiency
    flux_sky = calculate_flux(sky_brightness, zeropoint) * aperture_area * quantum_efficiency

    aperture_diameter = fwhm
    aperture_area_arcsec = math.pi * (aperture_diameter / 2) ** 2
    num_pixels = aperture_area_arcsec / (pixel_scale ** 2)

    signal_star = flux_star * exposure_time
    signal_sky = flux_sky * num_pixels * exposure_time
    noise_read = num_pixels * (read_noise ** 2)
    noise_dark = num_pixels * dark_current * exposure_time

    total_noise = math.sqrt(signal_star + signal_sky + noise_read + noise_dark)
    snr = signal_star / total_noise
    return snr

# Fungsi untuk menghitung waktu eksposur
def calculate_exposure_time(telescope, ccd, magnitude, snr_target, fwhm, airmass, filter_name, sky_brightness):
    telescope_data = telescopes[telescope]
    ccd_data = ccds[ccd]
    zeropoint = combinations[(telescope, ccd)]["zeropoint"]

    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2
    pixel_scale = ccd_data["pixel_size"] / 1000  # Konversi dari micrometer ke mm
    read_noise = ccd_data["read_noise"]
    dark_current = ccd_data["dark_current"]
    quantum_efficiency = ccd_data["quantum_efficiency"]

    extinction = k[filter_name]
    extinction_correction = extinction * (airmass - 1)
    flux_star = calculate_flux(magnitude + extinction_correction, zeropoint) * aperture_area * quantum_efficiency
    flux_sky = calculate_flux(sky_brightness, zeropoint) * aperture_area * quantum_efficiency

    aperture_diameter = fwhm
    aperture_area_arcsec = math.pi * (aperture_diameter / 2) ** 2
    num_pixels = aperture_area_arcsec / (pixel_scale ** 2)

    signal_sky = flux_sky * num_pixels
    noise_read = num_pixels * (read_noise ** 2)
    noise_dark = num_pixels * dark_current

    total_noise = math.sqrt(signal_sky + noise_read + noise_dark)
    exposure_time = (snr_target ** 2 * total_noise ** 2) / (flux_star ** 2)
    return exposure_time

def calculate_snr_and_exposure(magnitude, zeropoint, sky_brightness, aperture_area, pixel_scale, read_noise, dark_current, snr_target, filter_extinction, airmass):
    # Koreksi magnitudo untuk airmass
    mag_at_airmass = magnitude + (airmass - 1.0) * filter_extinction

    # Hitung flux dari objek (Nobj)
    Nobj = 10 ** (-0.4 * (mag_at_airmass - zeropoint))

    # Hitung flux dari latar belakang langit (Nbkgd)
    Nbkgd = 10 ** (-0.4 * (sky_brightness - zeropoint))

    # Hitung jumlah piksel dalam aperture
    aperture_diameter_arcsec = 3.0  # Diameter aperture dalam arcseconds
    Nas = math.pi / 4 * aperture_diameter_arcsec ** 2  # Area aperture dalam arcsec²
    Npix = Nas / (pixel_scale ** 2)  # Jumlah piksel dalam aperture

    # Hitung noise dari dark current dan read noise
    NeDark = Npix * dark_current  # Noise dari dark current
    NeRon = Npix * (read_noise ** 2)  # Noise dari read noise

    # Iterasi untuk menghitung exposure time
    t = 1.0  # Waktu eksposur awal dalam detik
    while True:
        # Hitung sinyal dari objek dan latar belakang selama waktu eksposur
        NeObj = Nobj * t
        NeBkgd = Nbkgd * t

        # Hitung SNR
        S_Nt = NeObj / math.sqrt(NeObj + NeBkgd + NeDark * t + NeRon)

        # Jika SNR target tercapai, keluar dari loop
        if S_Nt >= snr_target:
            break

        # Tambahkan waktu eksposur
        t += 1

    return S_Nt, t

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index_2.html", {"request": request})

@app.post("/calculate_exposure", response_class=HTMLResponse)
async def calculate_exposure(
    request: Request,
    telescope: str = Form(...),
    ccd: str = Form(...),
    magnitude: float = Form(...),
    snr_target: float = Form(...),
    fwhm: float = Form(...),
    airmass: float = Form(...),
    filter_name: str = Form(...),
    sky_brightness: float = Form(...),
):
    exposure_time = calculate_exposure_time(telescope, ccd, magnitude, snr_target, fwhm, airmass, filter_name, sky_brightness)
    return templates.TemplateResponse("result_2.html", {
        "request": request,
        "telescope": telescope,
        "ccd": ccd,
        "magnitude": magnitude,
        "snr_target": snr_target,
        "fwhm": fwhm,
        "airmass": airmass,
        "filter": filter_name,
        "sky_brightness": sky_brightness,
        "exposure_time": exposure_time,
    })

@app.post("/calculate_snr", response_class=HTMLResponse)
async def calculate_snr_endpoint(
    request: Request,
    telescope: str = Form(...),
    ccd: str = Form(...),
    magnitude: float = Form(...),
    exposure_time: float = Form(...),
    fwhm: float = Form(...),
    airmass: float = Form(...),
    filter_name: str = Form(...),
    sky_brightness: float = Form(...),
):
    logging.info(f"Received data: telescope={telescope}, ccd={ccd}, magnitude={magnitude}")
    snr = calculate_snr(telescope, ccd, magnitude, exposure_time, fwhm, airmass, filter_name, sky_brightness)
    return templates.TemplateResponse("result_2.html", {
        "request": request,
        "telescope": telescope,
        "ccd": ccd,
        "magnitude": magnitude,
        "exposure_time": exposure_time,
        "fwhm": fwhm,
        "airmass": airmass,
        "filter": filter_name,
        "sky_brightness": sky_brightness,
        "snr": snr,
    })

@app.post("/calculate_snr_and_exposure", response_class=HTMLResponse)
async def calculate_snr_and_exposure_endpoint(
    request: Request,
    telescope: str = Form(...),
    ccd: str = Form(...),
    magnitude: float = Form(...),
    sky_brightness: float = Form(...),
    snr_target: float = Form(...),
    filter: str = Form(...),
    airmass: float = Form(...),
):
    # Ambil data teleskop dan CCD
    telescope_data = telescopes[telescope]
    ccd_data = ccds[ccd]
    combination_data = combinations[(telescope, ccd)]

    # Ambil parameter dari teleskop dan CCD
    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2
    pixel_scale = ccd_data["pixel_size"] / 1000 / 206.265  # Konversi dari micrometer ke arcseconds
    read_noise = ccd_data["read_noise"]
    dark_current = ccd_data["dark_current"]
    zeropoint = combination_data["zeropoint"]
    filter_extinction = k[filter]

    # Hitung SNR dan waktu eksposur
    snr, exposure_time = calculate_snr_and_exposure(
        magnitude, zeropoint, sky_brightness, aperture_area, pixel_scale, read_noise, dark_current, snr_target, filter_extinction, airmass
    )

    return templates.TemplateResponse("result_2.html", {
        "request": request,
        "telescope": telescope,
        "ccd": ccd,
        "magnitude": magnitude,
        "sky_brightness": sky_brightness,
        "snr_target": snr_target,
        "filter": filter,
        "airmass": airmass,
        "snr": snr,
        "exposure_time": exposure_time,
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Las_cumbres:app", host="127.0.0.1", port=8000, reload=True)