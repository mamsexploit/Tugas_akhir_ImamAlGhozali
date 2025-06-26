from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import math
import matplotlib.pyplot as plt
import uvicorn

app = FastAPI()

# Mount static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Data teleskop dan CCD
telescopes = {
    "GSO": {"aperture": 0.254, "focal_length": 2.0},  
    "Celestron C11": {"aperture": 0.28, "focal_length": 2.8},
    "Teleskop Imam": {"aperture": 0.40, "focal_length": 2.8}
    #"Barride XX": {"aperture": 0.15, "focal_length": 8.0},
}

# Aperture in meters, focal length in meters
# barridenya yg versi apa? 

ccds = {
       "ZWO ASI 178MM": {"quantum_efficiency": 0.75, "read_noise": 3.0, "pixel_size": 2.4, "dark_current": 0},
    "ZWO ASI 2600 MM Pro": {"quantum_efficiency": 0.91, "read_noise": 1.5, "pixel_size": 3.76, "dark_current": 0.0022},
    "QHY 174 GPS": {"quantum_efficiency": 0.65, "read_noise": 2.0, "pixel_size": 5.86, "dark_current": 0},
    "ATIK 383L+": {"quantum_efficiency": 0.60, "read_noise": 5.3, "pixel_size": 5.4, "dark_current": 0.02}  # Tambah ATIK 383L+
}

# Kombinasi OTA dan CCD dengan zeropoint
combinations = {
    ("GSO", "ZWO ASI 178MM"): {"zeropoint": 25.12},
    ("GSO", "ZWO ASI 2600 MM Pro"): {"zeropoint": 25.45},
    ("GSO", "QHY 174 GPS"): {"zeropoint": 24.78},
    ("GSO", "ATIK 383L+"): {"zeropoint": 24.56},  # Tambah kombinasi GSO + ATIK
    ("Celestron C11", "ZWO ASI 178MM"): {"zeropoint": 25.23},
    ("Celestron C11", "ZWO ASI 2600 MM Pro"): {"zeropoint": 25.56},
    ("Celestron C11", "QHY 174 GPS"): {"zeropoint": 24.89},
    ("Celestron C11", "ATIK 383L+"): {"zeropoint": 24.67}, 
    ("Teleskop Imam", "QHY 174 GPS"): {"zeropoint": 24.67}  # Tambah kombinasi C11 + ATIK
}

# Satuan
# read noise: electron
# pixel_size: micrometer
# dark_current noise: electron/s/pixel @ 0 Celcius (diabaikan dulu)
# di cek lagi angkanya!


k = {"U": 0.25, "B": 0.7, "V": 1.21, "R": 0.21, "I": 0.21, "Clear": 0.1} # koefisien ekstingsi


# Daftar filter
filters = ["U", "B", "V", "R", "I", "Clear"]

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "telescopes": telescopes, "ccds": ccds, "filters": filters})

def calculate_exposure_time(signal_star, signal_sky, read_noise, dark_current, num_pixels, snr_target):
    # read_noise dan dark_current harus diambil dari ccd_data
    exposure_time = 1.0
    while True:
        # Signal dalam elektron
        signal = signal_star * exposure_time
        
        # Background noise dalam elektron
        sky_noise = signal_sky * num_pixels * exposure_time
        dark_noise = dark_current * num_pixels * exposure_time
        readout_noise = read_noise * read_noise * num_pixels
        
        # Total noise
        total_noise = math.sqrt(signal + sky_noise + dark_noise + readout_noise)
        
        # Calculate SNR
        snr_calculated = signal / total_noise
        
        if snr_calculated >= snr_target:
            break
            
        exposure_time += 1.0
        
        if exposure_time > 3600:  # 1 jam
            raise ValueError("Exposure time terlalu lama")
            
    return exposure_time

def calculate_exposure_time_analytic(signal_star, signal_sky, read_noise, dark_current, num_pixels, snr_target):
    """
    Menghitung exposure time dengan formula dari proposal tanpa redundansi
    """
    # Koefisien yang ada di Naskah Imam
    A = signal_star**2
    B = -(snr_target**2) * (signal_star + signal_sky*num_pixels + dark_current*num_pixels)
    C = -(snr_target**2) * (read_noise**2 * num_pixels)
    
    print("\nDebug coefficients:")
    print(f"A = {A:.2e}")
    print(f"B = {B:.2e}")
    print(f"C = {C:.2e}")
    
    # Hitung exposure time
    discriminant = B**2 - 4*A*C
    if discriminant < 0:
        raise ValueError("Tidak Boleh Nol")
    
    t = (-B + math.sqrt(discriminant)) / (2*A)
    
    # Hanya satu kali verifikasi
    signal = signal_star * t
    noise = math.sqrt(signal + 
                     signal_sky * num_pixels * t + 
                     dark_current * num_pixels * t + 
                     read_noise**2 * num_pixels)
    calculated_snr = signal / noise
    
    print(f"\nVerification:")
    print(f"Target SNR: {snr_target:.2f}")
    print(f"Calculated SNR: {calculated_snr:.2f}")
    print(f"Exposure time: {t:.2f} s")
    
    return t, calculated_snr  # Return both values to avoid recalculation

@app.post("/calculate_exposure", response_class=HTMLResponse)
async def calculate_exposure(
    request: Request,
    telescope: str = Form(...),
    ccd: str = Form(...),
    snr: float = Form(...),
    magnitude: float = Form(...),
    filter: str = Form(...),
    sky_brightness: float = Form(...),
    zenith_distance: float = Form(...),
    fwhm: float = Form(...),
):
    print("Endpoint /calculate dipanggil")
    # Validasi kombinasi OTA dan CCD
    if (telescope, ccd) not in combinations:
        raise ValueError(f"Kombinasi {telescope} dan {ccd} tidak valid.")

    # Ambil data teleskop, CCD, dan kombinasi
    telescope_data = telescopes[telescope]
    ccd_data = ccds[ccd]
    combination_data = combinations[(telescope, ccd)]

    # Hitung aperture area teleskop (dalam meter persegi)
    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2

    # Hitung ekstingsi atmosfer
    extinction = k[filter] * (1 / math.cos(math.radians(zenith_distance)))

    # Ambil quantum efficiency dari data CCD
    quantum_efficiency = ccd_data["quantum_efficiency"]

    # Hitung zeropoint dari kombinasi
    zeropoint = combination_data["zeropoint"]

    # Hitung jumlah piksel berdasarkan FWHM
    pixel_scale = 206.265 * ccd_data["pixel_size"] / (telescope_data["focal_length"] * 1000)
    num_pixels = calculate_pixels_in_aperture(fwhm, pixel_scale)

    # Hitung flux dan signal
    flux_star = 10 ** (-0.4 * (magnitude + extinction - zeropoint))
    flux_sky = 10 ** (-0.4 * (sky_brightness - zeropoint))

    # Konversi ke elektron (tanpa pembagi 3600)
    signal_star = flux_star * aperture_area * quantum_efficiency
    signal_sky = flux_sky * aperture_area * quantum_efficiency / num_pixels

    # Debug print
    print(f"\nDebug calculations:")
    print(f"Aperture area: {aperture_area:.2e} m²")
    print(f"Pixel scale: {pixel_scale:.2f} arcsec/pixel")
    print(f"Number of pixels: {num_pixels}")
    print(f"Signal star: {signal_star:.2f} e-/s")
    print(f"Signal sky: {signal_sky:.2f} e-/s/pixel")

    # Calculate exposure time
    try:
        exposure_time, verified_snr = calculate_exposure_time_analytic(
            signal_star,
            signal_sky,
            ccd_data["read_noise"],
            ccd_data["dark_current"],
            num_pixels,
            snr
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Tidak perlu verifikasi ulang karena SNR sudah dihitung
    return templates.TemplateResponse("result.html", {
        "request": request,
        "telescope": telescope,
        "ccd": ccd,
        "magnitude": magnitude,
        "exposure_time": exposure_time,
        "snr": verified_snr
    })

@app.post("/calculate_snr", response_class=HTMLResponse)
async def calculate_snr(
    request: Request,
    telescope: str = Form(...),
    ccd: str = Form(...),
    magnitude: float = Form(...),
    exposure_time: float = Form(...),
    filter: str = Form(...),
    sky_brightness: float = Form(...),
    zenith_distance: float = Form(...),
    fwhm: float = Form(...),  # FWHM sebagai input
):
    # Ambil data teleskop dan CCD
    telescope_data = telescopes[telescope]
    ccd_data = ccds[ccd]

    # Validasi kombinasi OTA dan CCD
    if (telescope, ccd) not in combinations:
        raise ValueError(f"Kombinasi {telescope} dan {ccd} tidak valid.")

    # Hitung ekstingsi atmosfer
    extinction = k[filter] * (1 / math.cos(math.radians(zenith_distance)))

    # Hitung flux_star menggunakan zeropoint dari kombinasi
    zeropoint = combinations[(telescope, ccd)]["zeropoint"]
    flux_star = 10 ** (-0.4 * (magnitude - zeropoint))

    # Konversi flux ke elektron
    gain = ccd_data.get("gain", 1.0)  # Default gain = 1.0 e-/ADU jika tidak ada
    flux_star = flux_star * gain

    # Hitung aperture area teleskop
    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2  # dalam meter^2

    # Hitung jumlah foton yang diterima oleh CCD
    quantum_efficiency = ccd_data["quantum_efficiency"]
    signal_star = flux_star * aperture_area * quantum_efficiency  # N_star

    # Hitung sky background
    flux_sky = 10 ** (-0.4 * sky_brightness)
    signal_sky = flux_sky * aperture_area * quantum_efficiency  # S

    # Hitung jumlah piksel berdasarkan FWHM dari input
    aperture_area_arcsec = math.pi * (fwhm / 2) ** 2  # Area lingkaran dalam arcsec²
    pixel_scale_arcsec = ccd_data["pixel_size"] / 1000 / 206.265  # Konversi pixel_size ke mm, lalu ke arcsec
    num_pixels = aperture_area_arcsec / (pixel_scale_arcsec ** 2)  # Konversi ke jumlah piksel
    num_pixels = max(num_pixels, 9)  # Minimal 9 piksel
    print(f"Number of Pixels (p): {num_pixels}")

    # Hitung noise sky
    noise_sky = math.sqrt(signal_sky * num_pixels * exposure_time)
    print(f"Noise Sky: {noise_sky}")

    # Hitung noise read
    read_noise = ccd_data["read_noise"]
    noise_read = math.sqrt(num_pixels) * read_noise
    print(f"Noise Read: {noise_read}")

    # Hitung dark current
    dark_current = ccd_data["dark_current"]  # e-/s/pixel
    noise_dark = math.sqrt(num_pixels * dark_current * exposure_time)
    print(f"Noise Dark: {noise_dark}")

    # Hitung total noise
    total_noise = math.sqrt((signal_star * exposure_time) + noise_sky + noise_read + noise_dark)

    # Hitung SNR
    snr = (signal_star * exposure_time) / total_noise
    print(f"SNR: {snr}")

    return templates.TemplateResponse("result.html", {
        "request": request,
        "telescope": telescope,
        "ccd": ccd,
        "magnitude": magnitude,
        "exposure_time": exposure_time,
        "filter": filter,
        "sky_brightness": sky_brightness,
        "zenith_distance": zenith_distance,
        "fwhm": fwhm,
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
    pixel_scale = ccd_data["pixel_size"] / 1000  # Konversi dari micrometer ke mm
    read_noise = ccd_data["read_noise"]
    dark_current = ccd_data["dark_current"]
    zeropoint = combination_data["zeropoint"]
    filter_extinction = k[filter]

    # Perbaikan perhitungan plate scale
    pixel_scale = 206.265 * ccd_data["pixel_size"] / (telescope_data["focal_length"] * 1000)  # arcsec/pixel

    # Hitung SNR dan waktu eksposur
    snr, exposure_time = calculate_snr_and_exposure_logic(
        magnitude, zeropoint, sky_brightness, aperture_area, pixel_scale, read_noise, dark_current, snr_target, filter_extinction, airmass
    )

    return templates.TemplateResponse("result.html", {
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

# Function to calculate SNR and exposure time
def calculate_snr_and_exposure_logic(
    magnitude, zeropoint, sky_brightness, aperture_area, pixel_scale, read_noise, dark_current, snr_target, filter_extinction, airmass
):
    extinction = filter_extinction * airmass
    flux_star = 10 ** (-0.4 * (magnitude - zeropoint + extinction))
    quantum_efficiency = 0.9  # Example value, adjust as needed
    signal_star = flux_star * aperture_area * quantum_efficiency

    flux_sky = 10 ** (-0.4 * sky_brightness)
    signal_sky = flux_sky * aperture_area * quantum_efficiency

    num_pixels = max(9, (1.5 / pixel_scale) ** 2 * math.pi)  # Example aperture area in pixels
    exposure_time = 1.0

    while True:
        noise_sky = math.sqrt(signal_sky * num_pixels * exposure_time)
        noise_read = math.sqrt(num_pixels) * read_noise
        noise_dark = math.sqrt(num_pixels * dark_current * exposure_time)
        total_noise = math.sqrt((signal_star * exposure_time) + noise_sky + noise_read + noise_dark)

        snr = (signal_star * exposure_time) / total_noise
        if snr >= snr_target or exposure_time > 3600:
            break
        exposure_time += 1.0

    return snr, exposure_time

# Perbaikan perhitungan area aperture dengan Gaussian PSF
def calculate_pixels_in_aperture(fwhm, pixel_scale):
    """
    Menghitung jumlah piksel dalam aperture dengan metode yang konsisten
    """
    radius_pixels = 1.5 * (fwhm / pixel_scale)  # 1.5 × FWHM radius
    area_pixels = math.pi * radius_pixels**2
    num_pixels = max(min(round(area_pixels), 100), 9)  # Batasi antara 9-100 piksel
    
    print(f"Aperture calculation:")
    print(f"FWHM: {fwhm:.2f} arcsec")
    print(f"Pixel scale: {pixel_scale:.2f} arcsec/pixel")
    print(f"Radius: {radius_pixels:.2f} pixels")
    print(f"Area: {area_pixels:.2f} pixels²")
    print(f"Final pixels: {num_pixels}")
    
    return num_pixels

def calculate_signal(magnitude, zeropoint, extinction, aperture_area, quantum_efficiency):
    """
    Menghitung signal dalam elektron/detik secara konsisten
    """
    flux = 10**(-0.4 * (magnitude + extinction - zeropoint))
    signal = flux * aperture_area * quantum_efficiency
    return signal

if __name__ == "__main__":
    uvicorn.run(
        "main2_24_march:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
