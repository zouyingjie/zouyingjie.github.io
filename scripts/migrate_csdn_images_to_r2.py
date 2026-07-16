#!/usr/bin/env python3
"""Upload CSDN inline images to Cloudflare R2 and rewrite Hugo Markdown links.

Required environment variables:
  R2_ENDPOINT         https://<account-id>.r2.cloudflarestorage.com
  R2_BUCKET           destination bucket name
  R2_ACCESS_KEY_ID    R2 API token access key
  R2_SECRET_ACCESS_KEY R2 API token secret
  R2_PUBLIC_BASE_URL  public R2/custom-domain URL, without a trailing slash

Run with --dry-run first. Without --apply no uploads or Markdown changes occur.
"""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
REQUIRED_ENV = (
    "R2_ENDPOINT",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_PUBLIC_BASE_URL",
)


def csdn_image_urls(post: Path) -> list[str]:
    urls = IMAGE_RE.findall(post.read_text())
    return sorted({url for url in urls if "csdnimg.cn" in url})


def download(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (CSDN migration)"})
    with urlopen(request, timeout=60) as response:
        return response.read(), response.headers.get_content_type()


def extension(url: str, content_type: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
        return suffix
    return mimetypes.guess_extension(content_type) or ".bin"


def upload(asset: bytes, content_type: str, object_key: str, config: dict[str, str]) -> None:
    endpoint = config["R2_ENDPOINT"].rstrip("/")
    bucket = quote(config["R2_BUCKET"], safe="")
    target = f"{endpoint}/{bucket}/{quote(object_key, safe='/')}"

    with tempfile.TemporaryDirectory() as temp_dir:
        asset_path = Path(temp_dir) / "asset"
        config_path = Path(temp_dir) / "curl.conf"
        asset_path.write_bytes(asset)
        config_path.write_text(
            "fail\n"
            "silent\n"
            "show-error\n"
            "location\n"
            'aws-sigv4 = "aws:amz:auto:s3"\n'
            f'user = "{config["R2_ACCESS_KEY_ID"]}:{config["R2_SECRET_ACCESS_KEY"]}"\n'
            f'upload-file = "{asset_path}"\n'
            f'header = "Content-Type: {content_type}"\n'
            f'url = "{target}"\n'
        )
        os.chmod(config_path, 0o600)
        subprocess.run(["curl", "--config", str(config_path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("posts", nargs="*", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    posts = args.posts or sorted(Path("content/posts").glob("*.md"))
    images = {post: csdn_image_urls(post) for post in posts}
    images = {post: urls for post, urls in images.items() if urls}
    total = sum(map(len, images.values()))
    print(f"{len(images)} posts, {total} CSDN image references")

    if args.dry_run or not args.apply:
        for post, urls in images.items():
            print(f"{post}: {len(urls)}")
        return

    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
    config = {name: os.environ[name] for name in REQUIRED_ENV}

    replacements: dict[str, str] = {}
    for url in sorted({url for urls in images.values() for url in urls}):
        asset, content_type = download(url)
        digest = hashlib.sha256(asset).hexdigest()
        object_key = f"images/csdn/{digest}{extension(url, content_type)}"
        upload(asset, content_type, object_key, config)
        replacements[url] = f"{config['R2_PUBLIC_BASE_URL'].rstrip('/')}/{object_key}"

    for post, urls in images.items():
        content = post.read_text()
        for url in urls:
            content = content.replace(url, replacements[url])
        post.write_text(content)
        print(f"rewrote {post}")


if __name__ == "__main__":
    main()
