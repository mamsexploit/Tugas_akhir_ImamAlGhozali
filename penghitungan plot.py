import numpy as np
import math
import matplotlib.pyplot as plt

# Ambil data dari main2_24_march.py
telescope_data = {
    "aperture": 0.28,  # Celestron C11
    "focal_length": 2.8
}

ccd_data = {
    "quantum_efficiency": 0.65,  # QHY 174 GPS
    "read_noise": 2.0,
    "pixel_size": 5.86,
    "dark_current": 0
}

# Parameter tetap
filter_name = "V"
sky_brightness = 17.5  # mag/arcsec²
zenith_distance = 30.0  # degrees
fwhm = 6.3  # pixels
zeropoint = 24.89  # Celestron C11 + QHY 174 GPS
k = 1.21  # koefisien ekstingsi untuk filter V

def calculate_snr(magnitude, exposure_time):
    # Hitung ekstingsi
    extinction = k * (1 / math.cos(math.radians(zenith_distance)))
    
    # Hitung flux bintang
    flux_star = 10 ** (-0.4 * (magnitude - zeropoint))
    aperture_area = math.pi * (telescope_data["aperture"] / 2) ** 2
    signal_star = flux_star * aperture_area * ccd_data["quantum_efficiency"]
    
    # Hitung sky background
    flux_sky = 10 ** (-0.4 * sky_brightness)
    signal_sky = flux_sky * aperture_area * ccd_data["quantum_efficiency"]
    
    # Hitung noise components
    num_pixels = math.pi * (1.5 * fwhm) ** 2
    
    noise_sky = math.sqrt(signal_sky * num_pixels * exposure_time)
    noise_read = math.sqrt(num_pixels) * ccd_data["read_noise"]
    noise_dark = math.sqrt(num_pixels * ccd_data["dark_current"] * exposure_time)
    total_noise = math.sqrt((signal_star * exposure_time) + noise_sky + noise_read + noise_dark)
    
    return (signal_star * exposure_time) / total_noise

# Plot 1: SNR tetap = 200, magnitude vs exposure time
magnitude_range = np.array([8, 9, 10, 11, 12, 13, 14, 15, 16])
exposure_times_calculated = []

for mag in magnitude_range:
    exp_time = 1.0
    while True:
        snr = calculate_snr(mag, exp_time)
        if snr >= 200 or exp_time > 3600:
            exposure_times_calculated.append(exp_time)
            break
        exp_time += 1.0

# Plot 2: Magnitude tetap = 11.5, exposure time vs SNR
exposure_range = np.array([1, 5, 10, 30, 60, 120, 180, 240, 300])
snr_values_calculated = []

fixed_magnitude = 11.5
for exp_time in exposure_range:
    snr = calculate_snr(fixed_magnitude, exp_time)
    snr_values_calculated.append(snr)

# Create two separate figures
# Plot 1: SNR tetap = 200, magnitude vs exposure time
plt.figure(figsize=(8, 6))
plt.plot(magnitude_range, exposure_times_calculated, 'b-o', linewidth=2)
plt.xlabel('Magnitude')
plt.ylabel('Exposure Time (s)')
plt.title(f'Exposure Time vs Magnitude (SNR={200})')
plt.grid(True)
plt.yscale('log')

# Buat custom y-ticks dengan interval yang lebih halus
y_ticks = [1, 2, 5, 10, 20, 50, 100, 200, 500]  # Nilai-nilai yang akan ditampilkan
plt.yticks(y_ticks, [str(y) for y in y_ticks])  # Set ticks dan labelnya

# Format y-axis dengan angka normal
plt.gca().yaxis.set_major_formatter(plt.ScalarFormatter())
plt.gca().yaxis.get_major_formatter().set_scientific(False)

# Add data labels
for i, txt in enumerate(exposure_times_calculated):
    plt.annotate(f'{txt:.1f}s', 
                (magnitude_range[i], exposure_times_calculated[i]),
                textcoords="offset points",
                xytext=(0,10),
                ha='center')

# Save first plot
plt.savefig('static/exposure_vs_magnitude.png')
plt.close()

# Plot 2: Magnitude tetap = 11.5, exposure time vs SNR
plt.figure(figsize=(8, 6))
plt.plot(exposure_range, snr_values_calculated, 'r-o', linewidth=2)
plt.xlabel('Exposure Time (s)')
plt.ylabel('SNR')
plt.title(f'SNR vs Exposure Time (Magnitude={fixed_magnitude})')
plt.grid(True)

# Add data labels
for i, txt in enumerate(snr_values_calculated):
    plt.annotate(f'{txt:.1f}', 
                (exposure_range[i], snr_values_calculated[i]),
                textcoords="offset points",
                xytext=(0,10),
                ha='center')

# Save second plot
plt.savefig('static/snr_vs_exposure.png')
plt.close()

# Print tables (existing code)
print("\nTabel 1: SNR Tetap = 200")
print("------------------------")
print("Magnitude | Exposure Time (s)")
print("------------------------")
for mag, exp in zip(magnitude_range, exposure_times_calculated):
    print(f"{mag:8.1f} | {exp:8.1f}")

print("\nTabel 2: Magnitude Tetap = 11.5")
print("------------------------")
print("Exp Time (s) | SNR")
print("------------------------")
for exp, snr in zip(exposure_range, snr_values_calculated):
    print(f"{exp:11.1f} | {snr:8.1f}")