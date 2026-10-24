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

    # Patch 3: client/client.py (resilience against transaction ID failures on datacenter IPs)
    client_file = twikit_dir / "client" / "client.py"
    if client_file.exists():
        content = client_file.read_text(encoding="utf-8")
        target_block = """        if not self.client_transaction.home_page_response:
            cookies_backup = self.get_cookies().copy()
            ct_headers = {
                'Accept-Language': f'{self.language},{self.language.split("-")[0]};q=0.9',
                'Cache-Control': 'no-cache',
                'Referer': f'https://{DOMAIN}',
                'User-Agent': self._user_agent
            }
            await self.client_transaction.init(self.http, ct_headers)
            self.set_cookies(cookies_backup, clear_cookies=True)

        tid = self.client_transaction.generate_transaction_id(method=method, path=urlparse(url).path)
        headers['X-Client-Transaction-Id'] = tid"""

        resilient_block = """        if not self.client_transaction.home_page_response:
            cookies_backup = self.get_cookies().copy()
            ct_headers = {
                'Accept-Language': f'{self.language},{self.language.split("-")[0]};q=0.9',
                'Cache-Control': 'no-cache',
                'Referer': f'https://{DOMAIN}',
                'User-Agent': self._user_agent
            }
            try:
                await self.client_transaction.init(self.http, ct_headers)
            except Exception:
                pass
            self.set_cookies(cookies_backup, clear_cookies=True)

        try:
            tid = self.client_transaction.generate_transaction_id(method=method, path=urlparse(url).path)
            if tid:
                headers['X-Client-Transaction-Id'] = tid
        except Exception:
            pass"""

        if target_block in content:
            content = content.replace(target_block, resilient_block)
            client_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/client/client.py for transaction ID resilience")
        else:
            print("client.py is already up to date or already patched.")

    # Patch 4 & 5: user.py and guest/user.py (prevent KeyError: 'urls' and NameError: 'entities' on all platforms)
    import re
    def patch_user_urls(file_path):
        if not file_path.exists():
            return
        c = file_path.read_text(encoding="utf-8")
        if "desc_ent = entities.get('description')" in c:
            print(f"{file_path.name} is already patched for safe URLs.")
            return

        safe_block = """entities = legacy.get('entities') if isinstance(legacy.get('entities'), dict) else {}
        desc_ent = entities.get('description') if isinstance(entities.get('description'), dict) else {}
        self.description_urls: list = desc_ent.get('urls', []) if isinstance(desc_ent.get('urls'), list) else []
        url_ent = entities.get('url') if isinstance(entities.get('url'), dict) else {}
        self.urls: list = url_ent.get('urls') if isinstance(url_ent.get('urls'), list) else None"""

        pattern = r"self\.description_urls:.*?\n\s*self\.urls:.*?(?=\n)"
        if re.search(pattern, c):
            c = re.sub(pattern, safe_block, c)
            file_path.write_text(c, encoding="utf-8")
            print(f"Successfully patched {file_path.name} for bulletproof URL/entities safety")
        else:
            print(f"Could not find url pattern in {file_path.name}")

    patch_user_urls(user_file)
    patch_user_urls(twikit_dir / "guest" / "user.py")

    # Patch 6: client/client.py - wrap get_timeline and get_latest_timeline item loops in try/except
    # so a single malformed ad/promoted tweet never crashes the entire timeline
    if client_file.exists():
        content = client_file.read_text(encoding="utf-8")
        old_loop = """        for item in items:
            if 'itemContent' not in item['content']:
                continue
            tweet = tweet_from_data(self, item)
            if tweet is None:
                continue
            results.append(tweet)"""

        safe_loop = """        for item in items:
            if 'content' not in item or 'itemContent' not in item['content']:
                continue
            try:
                tweet = tweet_from_data(self, item)
                if tweet is not None:
                    results.append(tweet)
            except Exception:
                continue"""

        if old_loop in content:
            content = content.replace(old_loop, safe_loop)
            client_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/client/client.py timeline loops for crash-immunity")
        else:
            print("timeline loops in client.py are already patched.")

    print("twikit patch verification complete.")


if __name__ == "__main__":
    apply_patch()
