# Fleet Maintenance Notes

## GLH

- `GLH` has shown a repeatable Ubuntu kernel-update edge case where `/boot/firmware` is mounted read-only during `flash-kernel`.
- Symptom:
  - `mv: cannot move '/boot/firmware/vmlinuz' to '/boot/firmware/vmlinuz.bak': Read-only file system`
- Recovery pattern:
  - `sudo mount -o remount,rw /boot/firmware`
  - `sudo dpkg --configure -a`
  - `sudo apt-get -f install -y`
  - `sudo apt-get -y autoremove`
  - `sudo mount -o remount,ro /boot/firmware`

## OSW MR2

- `oswmr2` also has a working alternate root login.
- The generated SSH config includes a dedicated alias:
  - `ssh oswmr2-root`
