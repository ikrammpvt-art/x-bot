"""
Automated patch script for twikit package.
Fixes the community issue with ondemand.s webpack chunk regex and user fields.
Automatically executed during Docker build or local setup.
"""
import site
import sys
from pathlib import Path


def apply_patch():
    print("Checking twikit installation...")
    site_packages_dirs = site.getsitepackages()
    if hasattr(site, "getusersitepackages"):
        site_packages_dirs.append(site.getusersitepackages())

    twikit_dir = None
    for sp in site_packages_dirs:
        candidate = Path(sp) / "twikit"
        if candidate.exists() and candidate.is_dir():
            twikit_dir = candidate
            break

    if not twikit_dir:
        # Check current python environment
        for p in sys.path:
            candidate = Path(p) / "twikit"
            if candidate.exists() and candidate.is_dir():
                twikit_dir = candidate
                break

    if not twikit_dir:
        print("twikit is not installed yet. Skipping patch.")
        return

    print(f"Found twikit at: {twikit_dir}")

    # Patch 1: transaction.py
    trans_file = twikit_dir / "x_client_transaction" / "transaction.py"
    if trans_file.exists():
        content = trans_file.read_text(encoding="utf-8")
        patched = False

        if "INDICES_REGEX = re.compile(r'\\[(\\d+)\\],\\s*16')" not in content:
            content = content.replace(
                "INDICES_REGEX = re.compile(r'\\((\\d+)\\,\\s*16\\)')",
                "INDICES_REGEX = re.compile(r'\\[(\\d+)\\],\\s*16')"
            )
            patched = True

        if 'r\',(\\d+):["\\\']ondemand\\.s["\\\']\'' not in content:
            content = content.replace(
                'r\'ondemand\\.s"?,?\\s*:?\\s*["\\\']([0-9a-f]+)["\\\']\'',
                'r\',(\\d+):["\\\']ondemand\\.s["\\\']\''
            )
            patched = True

        if patched:
            trans_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/x_client_transaction/transaction.py")
        else:
            print("transaction.py is already up to date.")

    # Patch 2: user.py
    user_file = twikit_dir / "user.py"
    if user_file.exists():
        content = user_file.read_text(encoding="utf-8")
        if "user_data['verified_type']" in content:
            content = content.replace(
                "verified_type = user_data['verified_type']",
                "verified_type = user_data.get('verified_type')"
            )
            content = content.replace(
                "is_blue_verified = user_data['is_blue_verified']",
                "is_blue_verified = user_data.get('is_blue_verified', False)"
            )
            user_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/user.py")
        else:
            print("user.py is already up to date.")

    print("twikit patch verification complete.")


if __name__ == "__main__":
    apply_patch()
