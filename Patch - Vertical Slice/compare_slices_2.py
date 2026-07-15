import numpy as np
import cv2
import matplotlib.pyplot as plt

def analyze_and_compare_slices(image_path=None, x_center=400, y_center=300, aperture_width=5):
    """
    Captures or loads an image and extracts BOTH horizontal and vertical 
    profiles simultaneously to evaluate the structural data differences.
    """
    # 1. Acquire Image Frame
    if image_path:
        frame = cv2.imread(image_path)
        if frame is None:
            print(f"Error: Could not load image from {image_path}. Generating dummy optical data for simulation.")
            frame = generate_simulated_frame()
    else:
        print("No image provided. Generating simulated spectrometer frame with horizontal dispersion...")
        frame = generate_simulated_frame()
        
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray_frame.shape
    half_w = aperture_width // 2
    
    # 2. Extract Slices Simutaneously from the exact same image state
    # Vertical Slice Extraction (Dispersion assumed vertical along Y-axis)
    vert_slice = gray_frame[:, x_center - half_w : x_center + half_w + 1]
    profile_vertical = np.mean(vert_slice, axis=1) # Length matches sensor height
    
    # Horizontal Slice Extraction (Dispersion assumed horizontal along X-axis)
    horiz_slice = gray_frame[y_center - half_w : y_center + half_w + 1, :]
    profile_horizontal = np.mean(horiz_slice, axis=0) # Length matches sensor width
    
    # 3. Calculate Physics Metrics
    print("======================================================================")
    print("                    DATA SLICE MATRIX COMPONENT SUMMARY                ")
    print("======================================================================")
    print(f"Sensor Resolutions Explored: Width (X) = {width} px | Height (Y) = {height} px")
    print(f"Aperture Width Selected: {aperture_width} px (Cross-averaging SNR Gain: {np.sqrt(aperture_width):.3f}x)")
    print(f"Horizontal Profile Array Shape: {profile_horizontal.shape} discrete bins")
    print(f"Vertical Profile Array Shape:   {profile_vertical.shape} discrete bins")
    print("----------------------------------------------------------------------")
    print(f"Horizontal Profile - Signal Variance: {np.var(profile_horizontal):.2f} | Dynamic Peak Range: {np.ptp(profile_horizontal)}")
    print(f"Vertical Profile   - Signal Variance: {np.var(profile_vertical):.2f} | Dynamic Peak Range: {np.ptp(profile_vertical)}")
    print("======================================================================")
    
    # 4. Generate Comparative Engineering Plots
    fig, axes = plt.subplots(2, 1, figsize=(10, 6))
    
    # Plot Horizontal Spectrum Axis
    axes[0].plot(profile_horizontal, color='blue', linewidth=1.5, label='Horizontal Profile I(x)')
    axes[0].set_title(f'Horizontal Slice Profile (Dispersion along Width X-Axis | Length: {width} bins)')
    axes[0].set_xlabel('Pixel Column Index (X)')
    axes[0].set_ylabel('Averaged Intensity')
    axes[0].grid(True, linestyle='--', alpha=0.6)
    axes[0].legend()
    
    # Plot Vertical Spectrum Axis
    axes[1].plot(profile_vertical, color='red', linewidth=1.5, label='Vertical Profile I(y)')
    axes[1].set_title(f'Vertical Slice Profile (Dispersion along Height Y-Axis | Length: {height} bins)')
    axes[1].set_xlabel('Pixel Row Index (Y)')
    axes[1].set_ylabel('Averaged Intensity')
    axes[1].grid(True, linestyle='--', alpha=0.6)
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig('slice_comparison_diagnostic.png', dpi=300)
    print("Diagnostic plot saved as 'slice_comparison_diagnostic.png'.")
    plt.show()

def generate_simulated_frame():
    """Generates a dummy 600x800 spectrometer capture with synthetic emission lines on X axis"""
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    # Generate 3 fake vertical emission columns (meaning dispersion is horizontal across X)
    peaks = [200, 450, 650]
    for x in range(800):
        intensity = 15 # baseline noise background
        for p in peaks:
            intensity += int(220 * np.exp(-((x - p) / 12)**2))
        img[:, x, :] = min(intensity, 255)
    # Add a slight vertical illumination drop-off at the edges of the slit
    for y in range(600):
        scale = np.exp(-((y - 300) / 200)**2)
        img[y, :, :] = (img[y, :, :] * scale).astype(np.uint8)
    return img

if __name__ == '__main__':
    # Run comparison test using the synthetic frame
    analyze_and_compare_slices()
