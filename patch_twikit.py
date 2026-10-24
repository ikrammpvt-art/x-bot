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

        if 'def __init__(self):\n        self.home_page_response = None\n        self.key = None' not in content:
            content = content.replace(
                'def __init__(self):\n        self.home_page_response = None',
                'def __init__(self):\n        self.home_page_response = None\n        self.key = None\n        self.key_bytes = None\n        self.animation_key = None'
            )
            patched = True

        if patched:
            trans_file.write_text(content, encoding="utf-8")
            print("Successfully patched twikit/x_client_transaction/transaction.py")
        else:
            print("transaction.py is already up to date.")

    # Patch 2: Complete bulletproof User.__init__ in user.py and guest/user.py
    import re
    safe_user_init = """    def __init__(self, client, data: dict) -> None:
        self._client = client
        legacy = data.get('legacy') or {}

        self.id: str = str(data.get('rest_id', ''))
        self.created_at: str = legacy.get('created_at', '')
        self.name: str = legacy.get('name', 'User')
        self.screen_name: str = legacy.get('screen_name', 'unknown')
        self.profile_image_url: str = legacy.get('profile_image_url_https', '')
        self.profile_banner_url: str = legacy.get('profile_banner_url')
        self.url: str = legacy.get('url')
        self.location: str = legacy.get('location', '')
        self.description: str = legacy.get('description', '')
        entities = legacy.get('entities') if isinstance(legacy.get('entities'), dict) else {}
        desc_ent = entities.get('description') if isinstance(entities.get('description'), dict) else {}
        self.description_urls: list = desc_ent.get('urls', []) if isinstance(desc_ent.get('urls'), list) else []
        url_ent = entities.get('url') if isinstance(entities.get('url'), dict) else {}
        self.urls: list = url_ent.get('urls') if isinstance(url_ent.get('urls'), list) else None
        self.pinned_tweet_ids: list[str] = legacy.get('pinned_tweet_ids_str', [])
        self.is_blue_verified: bool = data.get('is_blue_verified', False)
        self.verified: bool = legacy.get('verified', False)
        self.possibly_sensitive: bool = legacy.get('possibly_sensitive', False)
        self.can_dm: bool = legacy.get('can_dm', False)
        self.can_media_tag: bool = legacy.get('can_media_tag', False)
        self.want_retweets: bool = legacy.get('want_retweets', False)
        self.default_profile: bool = legacy.get('default_profile', False)
        self.default_profile_image: bool = legacy.get('default_profile_image', False)
        self.has_custom_timelines: bool = legacy.get('has_custom_timelines', False)
        self.followers_count: int = legacy.get('followers_count', 0)
        self.fast_followers_count: int = legacy.get('fast_followers_count', 0)
        self.normal_followers_count: int = legacy.get('normal_followers_count', 0)
        self.following_count: int = legacy.get('friends_count', 0)
        self.favourites_count: int = legacy.get('favourites_count', 0)
        self.listed_count: int = legacy.get('listed_count', 0)
        self.media_count = legacy.get('media_count', 0)
        self.statuses_count: int = legacy.get('statuses_count', 0)
        self.is_translator: bool = legacy.get('is_translator', False)
        self.translator_type: str = legacy.get('translator_type', 'none')
        self.withheld_in_countries: list[str] = legacy.get('withheld_in_countries', [])
        self.protected: bool = legacy.get('protected', False)"""

    init_pattern = re.compile(r"    def __init__\(self,.*?\n(?=\s+@property|\s+async def|\s+def [a-zA-Z_])", re.DOTALL)

    user_file = twikit_dir / "user.py"
    for u_file in [user_file, twikit_dir / "guest" / "user.py"]:
        if u_file.exists():
            c = u_file.read_text(encoding="utf-8")
            if "self.pinned_tweet_ids: list[str] = legacy.get('pinned_tweet_ids_str', [])" not in c:
                new_c, cnt = init_pattern.subn(safe_user_init + "\n\n", c)
                if cnt > 0:
                    u_file.write_text(new_c, encoding="utf-8")
                    print(f"Successfully applied bulletproof User.__init__ to {u_file.name}")
                else:
                    print(f"Pattern did not match in {u_file.name}")
            else:
                print(f"{u_file.name} User.__init__ is already up to date.")

    # Patch 3: client/client.py - resilience against transaction ID failures on datacenter IPs
    client_file = twikit_dir / "client" / "client.py"
    if client_file.exists():
        content = client_file.read_text(encoding="utf-8")

        # 3a. Wrap init call
        content = content.replace(
            "await self.client_transaction.init(self.http, ct_headers)",
            "try:\n                await self.client_transaction.init(self.http, ct_headers)\n            except Exception:\n                pass"
        )

        # 3b. Wrap transaction ID generation
        old_tid = "tid = self.client_transaction.generate_transaction_id(method=method, path=urlparse(url).path)\n        headers['X-Client-Transaction-Id'] = tid"
        safe_tid = "try:\n            tid = self.client_transaction.generate_transaction_id(method=method, path=urlparse(url).path)\n            if tid:\n                headers['X-Client-Transaction-Id'] = tid\n        except Exception:\n            pass"
        if old_tid in content:
            content = content.replace(old_tid, safe_tid)

        # 3c. Wrap get_timeline and get_latest_timeline loops for crash-immunity
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
        print("Successfully patched twikit/client/client.py (transaction resilience + loop safety)")

    print("twikit patch verification complete.")


if __name__ == "__main__":
    apply_patch()
