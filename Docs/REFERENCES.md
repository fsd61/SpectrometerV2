# References

Papers behind the analysis methods in SpectrometerV2, with what each one means
for this code. Links go to the publisher and, where one exists, a free copy
from the authors or PubMed Central. The papers themselves are not
redistributed here.

## Simulated annealing line fitting

**DiGennaro, F. S. & Cowburn, D.** Parametric estimation of time-domain NMR
signals using simulated annealing. *Journal of Magnetic Resonance* 96, 582–588
(1992). A copy is included: [Journal.Mag.Res.96.pdf](Journal.Mag.Res.96.pdf).

**Cowburn, D., Glushka, J., DiGennaro, F. & Rios, C. B.** Parametric estimation
in 1-D, 2-D, and 3-D NMR. In J. C. Hoch, F. M. Poulsen & C. Redfield (eds.),
*Computational Aspects of the Study of Biological Macromolecules by Nuclear
Magnetic Resonance Spectroscopy*, NATO ASI Series A: Life Sciences, vol. 225,
27–38. Plenum Press, New York (1991). The companion paper on the same group's
parametric estimation work: extracting line positions and intensities from
noisy spectra as fitted parameters rather than reading them off the trace.

The basis of `analysis/annealing.py` and the line fitting in
`analysis/linefit.py`: the auto-tuned starting temperature, Markov chains scaled
to the number of lines, and the quench to fast final convergence. SpectrometerV2
adds a Levenberg-Marquardt polish after the anneal (see the README for why).
Primer: [simulated_annealing_primer.pdf](simulated_annealing_primer.pdf).

## Wavelets

**Daubechies, I.** Orthonormal bases of compactly supported wavelets.
*Communications on Pure and Applied Mathematics* 41(7), 909–996 (1988).
[doi:10.1002/cpa.3160410705](https://doi.org/10.1002/cpa.3160410705) ·
[free copy from the author](https://sites.math.duke.edu/~ingrid/publications/cpam41-1988.pdf)

The paper that constructs the compactly supported orthonormal wavelets the
denoiser is built on. The `db4` and `db6` choices in `[wavelet]` are from this
family; `sym5` (the default) and `coif3` are later, nearly symmetric variants of
the same construction, preferred here because they do not pull line centers.

**Donoho, D. L. & Johnstone, I. M.** Ideal spatial adaptation by wavelet
shrinkage. *Biometrika* 81(3), 425–455 (1994).
[doi:10.1093/biomet/81.3.425](https://doi.org/10.1093/biomet/81.3.425)

The universal threshold σ·√(2 ln N) with σ estimated from the finest detail
coefficients (median absolute deviation / 0.6745). `wavelet_denoise` uses it,
scaled by `threshold_scale`; the default of 0.6 is gentler than the paper's 1.0
because, measured on simulated 4-px lines, the full threshold with soft
shrinkage left a dim line at 43% of its height.

**Coifman, R. R. & Donoho, D. L.** Translation-invariant de-noising. In
*Wavelets and Statistics*, Lecture Notes in Statistics 103, 125–150, Springer
(1995). [doi:10.1007/978-1-4612-2544-7_9](https://doi.org/10.1007/978-1-4612-2544-7_9) ·
[free copy from the author](https://web.stanford.edu/dept/statistics/cgi-bin/donoho/wp-content/uploads/2018/08/TIDeNoise.pdf)

Cycle spinning: denoise at several circular shifts and average, so the result
no longer depends on where a line falls on the wavelet grid. This is the
`shifts` setting (default 8).

**Srivastava, M., Dzikovski, B. & Freed, J. H.** Extraction of weak
spectroscopic signals with high fidelity: examples from ESR. *Journal of
Physical Chemistry A* 125(20), 4480–4487 (2021).
[doi:10.1021/acs.jpca.1c02241](https://doi.org/10.1021/acs.jpca.1c02241) ·
[free author manuscript (PubMed Central)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8317606/)

Wavelet denoising applied to spectra, including overlapped lines and weak lines
next to strong ones, with recovery reported down to an SNR of about 1. Their
method (NERD) adds signal identification in the wavelet domain on top of
improved thresholding; it is more advanced than the cycle-spun thresholding
implemented here, and a candidate for future work on weak lines. Software:
[denoising.cornell.edu](https://denoising.cornell.edu).

Primer: [wavelet_transforms_primer.pdf](wavelet_transforms_primer.pdf).
