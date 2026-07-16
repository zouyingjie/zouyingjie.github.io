#!/usr/bin/env python3
"""Upload CSDN inline images with the local Upload to R2 service.

The Automator service owns the R2 credentials. This script only downloads images,
passes local files to that service, and rewrites links after each upload succeeds.
Run with --dry-run first. Without --apply no uploads or Markdown changes occur.
"""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
DEFAULT_UPLOADER = Path("/Users/jinyinhuacha/study/utils/upload-R2/upload_to_r2.py")
PUBLIC_URL_RE = re.compile(r"https?://\S+")


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


def upload(asset: bytes, object_name: str, uploader: Path) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        asset_path = Path(temp_dir) / object_name
        asset_path.write_bytes(asset)
        result = subprocess.run(
            ["/Users/jinyinhuacha/miniconda3/bin/python3", str(uploader), str(asset_path)],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stdout.strip() or result.stderr.strip())
        urls = PUBLIC_URL_RE.findall(result.stdout)
        if not urls:
            raise RuntimeError(f"Uploader returned no public URL: {result.stdout.strip()}")
        return urls[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("posts", nargs="*", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uploader", type=Path, default=DEFAULT_UPLOADER)
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

    if not args.uploader.is_file():
        raise SystemExit(f"Upload to R2 service not found: {args.uploader}")

    replacements: dict[str, str] = {}
    for url in sorted({url for urls in images.values() for url in urls}):
        asset, content_type = download(url)
        digest = hashlib.sha256(asset).hexdigest()
        object_name = f"csdn-{digest}{extension(url, content_type)}"
        replacements[url] = upload(asset, object_name, args.uploader)

    for post, urls in images.items():
        content = post.read_text()
        for url in urls:
            content = content.replace(url, replacements[url])
        post.write_text(content)
        print(f"rewrote {post}")


if __name__ == "__main__":
    main()
