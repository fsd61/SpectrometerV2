half_w = APERTURE_WIDTH // 2

if DISPERSION_MODE == 'vertical':
    # Vertical Dispersion Tracking: Slice vertically, average horizontally
    vertical_slice = gray_frame[:, X_CENTER - half_w : X_CENTER + half_w + 1]
    profile_1d = np.mean(vertical_slice, axis=1)  # axis=1 compresses columns
else:
    # Horizontal Dispersion Tracking: Slice horizontally, average vertically
    horizontal_slice = gray_frame[Y_CENTER - half_w : Y_CENTER + half_w + 1, :]
    profile_1d = np.mean(horizontal_slice, axis=0)  # axis=0 compresses rows