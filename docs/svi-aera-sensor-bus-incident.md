# SVI Aera sensor-bus incident — 2026-07-19

SVI MR1 (`svimr1`, Aera) remains online through its intended external MediaTek
USB Wi-Fi adapter `wlx7419f8176191`. The built-in `wlan0` is disconnected. The
external route, address `10.234.23.9`, and strong approximately -41 dBm link were
unchanged before and after recovery work; no fleet action changed either SVI
network profile.

The website stopped receiving temperatures because the shared 1-Wire bus failed,
not because the Pi went offline. Service logs show normal readings through
05:42:50 EDT on July 19. At 05:43:04 all five probes became unreadable together;
the last backend update was 05:44:30. By the 05:45 audit, the kernel master had
zero slaves. The configured GPIO4 overlay remains present, GPIO4 reads high, the
three 1-Wire modules are loaded, power/throttle flags are zero, and the approved
sensor application and dependencies remain intact.

On July 21, a bounded recovery stopped only `mri-sensor.service`, unloaded and
reloaded `w1_gpio` and `w1_therm`, waited for enumeration, restarted the service,
and proved the external USB route unchanged. No probe returned. One controlled
reboot then returned the same external USB route, Tailscale, kernel, application,
and service, but all five probes and production telemetry remained absent.
Guarded report `reboot_20260721_073224.json` correctly records
`verification_failed`; no further warm reboot is authorized by that result.

The next useful action is onsite inspection of the common sensor path: 3.3 V,
ground, GPIO4 data connector, pull-up resistor, and the first shared junction.
Because all five sensors failed within seconds, replacing individual probes is
not the first step. After repair, require all five exact IDs below, an active
service that stays running, and advancing `SVIMR1` backend telemetry:

- `28-34fa0087f382`
- `28-481b0087611d`
- `28-64410087c637`
- `28-68b7008720ea`
- `28-6b940087d30e`
