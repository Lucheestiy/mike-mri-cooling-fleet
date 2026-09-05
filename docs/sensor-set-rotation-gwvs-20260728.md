# GWVS sensor-set calibration and deployment rotation

## Set 1 — planned for AGC MR2

The first new five-probe set was bundled and calibrated on GWVS on 2026-07-28.
It is planned to replace AGC MR2's current four-probe set.

Calibration used 60 direct 1-Wire samples from 15:29:58Z through 15:43:53Z.
Each offset normalizes that probe's mean to the grand mean of all five probes:

| Probe ID | Mean °C | Offset °C |
|---|---:|---:|
| `28-0000006ebc26` | 23.446650 | -0.1069 |
| `28-000000703ac4` | 23.214350 | +0.1254 |
| `28-00000070a421` | 23.358083 | -0.0183 |
| `28-00000070c02b` | 23.382033 | -0.0423 |
| `28-00000070d37a` | 23.297667 | +0.0421 |

Correction formula: `corrected temperature = raw temperature + offset`.

The relative offsets agreed within a few thousandths of a degree when calculated
over the final 10, 20, and 30 samples, despite the bundle cooling during the run.
Raw evidence is retained in `reports/gwvs_set1_bundled_20260728.csv`.

Before enabling AGC MR2 publishing, record which physical serial number is
installed on each of the five channels and update AGC MR2's host variables.

### AGC MR2 installation and mapping

Installed on 2026-07-28. Twelve direct signature samples were compared with
AGC MR2's established channel ranges. The resulting mapping is:

| Channel | Probe ID | Corrected signature mean °C |
|---|---|---:|
| Helium in | `28-00000070a421` | 20.8200 |
| Helium out | `28-00000070d37a` | 34.4378 |
| Primary in | `28-00000070c02b` | 13.1240 |
| Primary out | `28-0000006ebc26` | 14.2784 |
| Room | `28-000000703ac4` | 21.1979 |

This matches the prior AGC MR2 signature: helium approximately 20.5/35 °C and
primary approximately 13–14 °C, with the colder primary channel assigned as
inlet and the warmer channel as outlet. Raw deployment evidence is retained in
`reports/agcmr2_new_set_signature_20260728.csv`.

## Set 2 — deployed at SVI Aera

Connect the second five-probe set to GWVS, bundle all five probes together, let
them equalize for at least 10–15 minutes, then repeat the recorded calibration
procedure. Validate clean enumeration and repeated reads on GWVS before moving
the set to SVI MR1 Aera (`svimr1`).

Completed on GWVS on 2026-07-28: 67 valid readings per probe over 16 minutes,
with no missing or 85 °C sentinel readings. The final 30-sample stable window
produced these portable offsets:

| Probe ID | Stable-window mean °C | Offset °C |
|---|---:|---:|
| `28-000000b2d54b` | 23.751833 | -0.0062 |
| `28-000000b323cc` | 23.678933 | +0.0667 |
| `28-000000b48d28` | 23.664367 | +0.0812 |
| `28-000000b958ec` | 23.893500 | -0.1479 |
| `28-000000ba3e06` | 23.739300 | +0.0063 |

Raw evidence is retained in `reports/gwvs_set2_svi_bundled_20260728.csv`.
Installed at SVI MR1 on 2026-07-29. All five probes enumerated, resolving the
previous bus-wide fault. Direct live signatures, corrected with the portable
offsets above, were compared with the Aera's historical channel ranges. The
mapping is:

| Channel | Probe ID | Corrected signature mean °C |
|---|---|---:|
| Helium in | `28-000000b48d28` | 21.9331 |
| Helium out | `28-000000b323cc` | 29.4665 |
| Primary in | `28-000000b2d54b` | 11.6040 |
| Primary out | `28-000000ba3e06` | 13.3039 |
| Room | `28-000000b958ec` | 21.5685 |

Raw deployment evidence is retained in
`reports/svimr1_set2_signature_20260729.csv`.

## Set 3 — final GWVS set

Connect and bundle-calibrate the third five-probe set on GWVS using the same
procedure. Preserve its serial-number offsets before separating or installing
the probes. This set will remain at GWV Magnetom Sola.

Completed on GWVS on 2026-07-28: 70 valid readings per probe over 16 minutes,
with no missing or 85 °C sentinel readings. The user bonded the probes after
acquisition began, so offsets use the final 50-sample post-bonding window:

| Probe ID | Post-bonding mean °C | Offset °C |
|---|---:|---:|
| `28-0000006ff252` | 23.508520 | +0.3480 |
| `28-000000700c77` | 24.081000 | -0.2245 |
| `28-000000708c2c` | 23.784760 | +0.0717 |
| `28-00000070af65` | 23.970980 | -0.1145 |
| `28-0000007100e4` | 23.937220 | -0.0807 |

The raw probe spread of roughly 0.6 °C was consistent probe bias: offsets from
the final 20/30/40/50-sample windows agreed within about 0.004 °C. Raw evidence
is retained in `reports/gwvs_set3_permanent_bundled_20260728.csv`. After
applying the offsets, an eight-reading live verification produced a corrected
mean spread of 0.0660 °C across all five probes.
