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

    # Patch 4: guest/user.py (prevent KeyError: 'urls' on users without description URLs)
    guest_user_file = twikit_dir / "guest" / "user.py"
    if guest_user_file.exists():
        content = guest_user_file.read_text(encoding="utf-8")
        patched = False
        target_urls = "self.description_urls: list = legacy['entities']['description']['urls']"
        safe_urls = "self.description_urls: list = legacy.get('entities', {}).get('description', {}).get('urls', []) if isinstance(legacy.get('entities'), dict) else []"
        if target_urls in content:
            content = content.replace(target_urls, safe_urls)
            patched = True

        target_url = "self.urls: list = legacy['entities'].get('url', {}).get('urls')"
        safe_url = "self.urls: list = legacy.get('entities', {}).get('url', {}).get('urls') if isinstance(legacy.get('entities'), dict) else None"
        if target_url in content:
            content = content.replace(target_url, safe_url)
            patched = True

        if patched:
            guest_user_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/guest/user.py for safe url handling")
        else:
            print("guest/user.py is already up to date.")

    # Patch 5: user.py entities safety
    if user_file.exists():
        content = user_file.read_text(encoding="utf-8")
        patched = False
        target_u1 = "self.description_urls: list = legacy['entities'].get('description', {}).get('urls', [])"
        safe_u1 = "entities = legacy.get('entities') or {}\n        self.description_urls: list = entities.get('description', {}).get('urls', []) if isinstance(entities.get('description'), dict) else []"
        if target_u1 in content:
            content = content.replace(target_u1, safe_u1)
            patched = True

        target_u2 = "self.urls: list = legacy['entities'].get('url', {}).get('urls')"
        safe_u2 = "self.urls: list = entities.get('url', {}).get('urls') if isinstance(entities.get('url'), dict) else None"
        if target_u2 in content:
            content = content.replace(target_u2, safe_u2)
            patched = True

        if patched:
            user_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/user.py for safe entities handling")

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
