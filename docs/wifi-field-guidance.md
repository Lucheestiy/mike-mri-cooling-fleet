# Wi-Fi field guidance

## Current routed-link findings

Read-only diagnostics on 2026-07-16 found four live links at or below the fleet's
`-67 dBm` remote-maintenance floor. All four are Raspberry Pi 5 onboard
`brcmfmac` radios on 5 GHz, all currently use `wlan0` for the default route, and
none has a USB Wi-Fi radio attached. Values below are from complete audit
`audit_20260716_234347.json`; negotiated rates can vary between samples.

| Pi | Observed link | Evidence-based action |
| --- | --- | --- |
| AGC MR1 | -73/-74 dBm, onboard 5805 MHz; four 30-packet gateway samples had 0% loss and 5.1–5.5 ms average | Nearby: move the Pi/antenna away from metal and the NVMe/USB cabling, then remeasure. A reversible power-save A/B test showed no RSSI or latency benefit, so leave power saving unchanged. Add an external-antenna adapter or Ethernet if it remains below -67 dBm. |
| GMC EP3 | -69 dBm, onboard 5765 MHz; 57.7/86.6 Mbit/s RX/TX | Nearby: reposition and remeasure. A reversible power-save A/B test at an earlier weaker sample did not improve RSSI or consistently improve latency, so leave power saving unchanged. |
| Jersey Shore MR | -71 dBm, onboard 5240 MHz; 86.6/86.6 Mbit/s RX/TX | Remote: reposition and remeasure before any update or reboot. If it remains below -67 dBm, install an external-antenna adapter or Ethernet. |
| VWM2 | -80 dBm, onboard 5745 MHz; 13/12 Mbit/s RX/TX | Critical: install Ethernet or a dual-band USB adapter with an external antenna. Weak signal is advisory rather than a maintenance blocker; require current reachability, backup/restore, health, telemetry, and storage gates and use the persistent local upgrade unit. |

Some site gateways did not answer ICMP echo while the Pis remained reachable over
Tailscale. That is not counted as packet loss evidence; gateway firewalls commonly
drop echo. RSSI, negotiated rates, routed interface, Tailscale reachability, and
repeated fleet audits remain the decision evidence.

## Adapter requirements

Prefer Ethernet where installation is practical. For USB Wi-Fi, use a dual-band
adapter with a movable external antenna and in-kernel Linux support for the Pi's
current and target Ubuntu kernels. Avoid making fleet recovery depend on an
unmaintained vendor-only DKMS driver. Place the antenna outside or away from the
metal scanner cabinet, SSD/NVMe carrier, USB 3 cable, and power supply.

Do not disable the onboard radio during initial installation. Establish the new
connection, confirm its default route, DNS, SSH, Tailscale, sensor service, exact
probes, and fresh CoolMRI telemetry, then observe it before lowering the onboard
route priority. This preserves an immediate fallback if the USB adapter or its
driver fails after an update.

## Acceptance test after repositioning or hardware installation

1. Require the intended adapter—not the old `wlan0` route—to carry the default
   route when a USB adapter was installed.
2. Record interface, driver, adapter type, frequency, RX/TX rates, power-save
   state, and RSSI in two audits at least five minutes apart.
3. Target better than -67 dBm; better than -60 dBm is preferred for unattended
   remote reboot work. Never proceed at or below -75 dBm.
4. Confirm Tailscale and SSH remain reachable, the expected MRI/CV service is
   active, every configured 1-Wire probe is present, throttle flags are zero, and
   server telemetry advances.
5. Only then rerun the standard mutation preflight. Do not use a momentary strong
   reading as authorization for a package update or reboot.

## GMC EP3 reversible power-save experiment

The nearby test alternated the live radio between power save on/off twice, sampled
30 gateway packets in each state, and restored the original `on` state before the
command exited. All four samples had 0% loss. RSSI remained -78/-79 dBm; high
latency variation appeared in one on and one off sample, while the second pair was
about 5–6 ms in both modes. The CV sensor service stayed active. This is evidence
against a persistent software toggle as the remedy; improve the physical radio
path instead. The saved NetworkManager profile was never changed.

## AGC MR1 reversible power-save experiment

The nearby 2026-07-17 test used the same guarded method: live power saving was
alternated on/off twice, with 30 gateway packets in every state and an exit trap
that restored the original `on` state. All 120 packets returned. RSSI stayed at
-73/-74 dBm, while average latency was 5.07 and 5.28 ms with power saving on and
5.46 and 5.32 ms with it off. The sensor service, five probes, link, and zero
throttle state passed afterward, and the saved NetworkManager profile was never
changed. Persistent power-save changes are therefore not recommended; improve
placement, antenna path, or use Ethernet/external-antenna hardware instead.
