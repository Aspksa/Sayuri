# Sayuri — media and release guidance
- `assets/images/sayuri/avatar-main.webp`: 96px optimized preview derived from supplied Sayuri portrait.
- `web/assets/avatar.webp`: identical public preview for the chat UI.
- The full-resolution source stays with its owner; upload it separately when publishing a release, if redistribution rights permit.
- `updater.py` checks the latest GitHub Release and does **not** silently execute downloaded code. Release packaging, signature checks, atomic installation and rollback are still required.
