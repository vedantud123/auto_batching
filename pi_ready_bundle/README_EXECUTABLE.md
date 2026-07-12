# Build Executable on Raspberry Pi

Use these commands on Raspberry Pi inside this folder:

```bash
cd /path/to/pi_ready_bundle
chmod +x build_rpi_executable.sh
./build_rpi_executable.sh
```

This creates:
- `auto_batching_app` (Linux executable, no `.py` needed to run)

Run it:

```bash
./auto_batching_app
```

Notes:
- Build must be done on Raspberry Pi itself (ARM build for ARM device).
- A Linux executable is produced (not Windows `.exe`).
- You can remove `.py` files after successful build if you want to hide source from normal users.
