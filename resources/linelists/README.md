# Pinned line lists

This directory holds **pinned** NIST ASD exports used as reference wavelength
atlases. It is intentionally empty of data files in the repository: an atlas is
calibration input, and one whose provenance cannot be attested is worse than
none at all. Generate your own and commit it here.

## Why pin rather than query

ASD is revised. A wavelength solution stored today and re-checked next year must
be comparable against *the same* line data, or the comparison is meaningless.
`linelist.load_line_list` hashes the file it reads and folds that hash into
`LineList.fingerprint()`, which belongs in the calibration record next to the
capture backend identity — same reasoning as `data.schema_core`.

Live querying is deliberately not implemented.

## Producing an export

1. Open the ASD Lines form: <https://physics.nist.gov/PhysRefData/ASD/lines_form.html>
2. **Spectrum**: e.g. `Ar I` (the FS-2 starter is argon-filled).
3. **Wavelength range**: `600` to `940` nm to match the current operating band.
4. **Wavelength in**: choose **air** (the default above 200 nm) *or* vacuum —
   whichever you pick, keep the column headers, because the parser reads the
   convention from `obs_wl_air(nm)` vs `obs_wl_vac(nm)` and refuses to guess.
5. Under **Additional Criteria / Show**, enable:
   - Observed wavelength, Ritz wavelength
   - Relative intensity
   - **Transition probability (`Aki`)** — required for modelled intensities
   - **Energy level data (`Ei`, `Ek`) and statistical weights (`g_i`, `g_k`)**
6. **Format output**: *Tab-delimited* (`format=3`).
7. Save as `<species>_<range>_<version>.tsv`, e.g. `ar_i_600_940_v1.tsv`.

Without step 5 the file still parses, but every line reports
`has_boltzmann_terms() == False` and `usable_lines()` will drop it rather than
invent an amplitude.

## Provenance sidecar

Alongside `ar_i_600_940_v1.tsv`, write `ar_i_600_940_v1.tsv.provenance.json`:

```json
{
  "source": "NIST ASD Lines — Ar I, 600–940 nm, air wavelengths",
  "retrieved": "2026-08-24",
  "query": "https://physics.nist.gov/cgi-bin/ASD/lines1.pl?spectra=Ar+I&low_w=600&upp_w=940&unit=1&format=3",
  "notes": "ASD v5.12. Ritz wavelengths preferred where present."
}
```

The sidecar is optional — the content hash is computed either way — but a list
without one can say what it contains and never where it came from.

## Air vs. vacuum

Above 200 nm ASD defaults to **standard air**. The difference is ~0.22 nm at
810 nm, which is the same order as this instrument's best-case resolution, so it
is a real error rather than a rounding detail. Conversions use Peck & Reeder
(1972), the same formula ASD uses. Whichever convention a stored calibration was
fitted in must be recorded with it; `LineList.describe()` emits the fields for
exactly that.

## Not a substitute

`tests/fixtures/nist_ar_i_sample.tsv` is a small hand-entered fixture for unit
tests. Its transition probabilities are approximate. Do not use it as an atlas.
