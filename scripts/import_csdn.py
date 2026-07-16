#!/usr/bin/env python3
"""Convert saved CSDN article sources into Hugo Markdown drafts.

Prefer saving the source Markdown from the CSDN editor as <article-id>.md. HTML
pages (<article-id>.html) are supported as a fallback. New posts are drafts by
design so that images can be migrated and the content can be reviewed first.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag


IGNORED_CLASSES = {"contentImg-no-view", "look-more-preCode", "pre-numbering"}


def clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def inline(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return str(node)

    if node.name == "br":
        return "\n"
    if node.name == "img":
        classes = set(node.get("class", []))
        src = node.get("src") or node.get("data-src")
        if not src or classes & IGNORED_CLASSES:
            return ""
        return f"![{node.get('alt', '').strip()}]({src})"

    if node.name == "i" and "words-blog-icon" in node.get("class", []):
        return ""

    value = "".join(inline(child) for child in node.children)
    if node.name in {"strong", "b"}:
        return f"**{value.strip()}**"
    if node.name in {"em", "i"}:
        return f"*{value.strip()}*"
    if node.name == "code":
        return f"`{value.strip()}`"
    if node.name == "a":
        href = node.get("href", "").strip()
        text = value.strip() or href
        return f"[{text}]({href})" if href else text
    return value


def language_for(node: Tag) -> str:
    code = node.find("code")
    if not code:
        return ""
    for class_name in code.get("class", []):
        if class_name.startswith("language-"):
            return class_name.removeprefix("language-")
    return ""


def block(node: Tag) -> str:
    if node.name == "pre":
        source = node.get_text("", strip=False).replace("\u00a0", " ").strip("\n")
        return f"```{language_for(node)}\n{source}\n```\n\n"

    if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return f"{'#' * int(node.name[1])} {clean_text(inline(node))}\n\n"
    if node.name == "p":
        value = clean_text(inline(node))
        return f"{value}\n\n" if value else ""
    if node.name == "blockquote":
        value = clean_text(inline(node))
        return "\n".join(f"> {line}" for line in value.splitlines()) + "\n\n"
    if node.name in {"ul", "ol"}:
        lines = []
        for index, item in enumerate(node.find_all("li", recursive=False), start=1):
            marker = f"{index}." if node.name == "ol" else "-"
            nested_lists = item.find_all(["ul", "ol"], recursive=False)
            for nested_list in nested_lists:
                nested_list.extract()
            value = clean_text(inline(item))
            lines.append(f"{marker} {value}")
            lines.extend(block(nested_list).rstrip() for nested_list in nested_lists)
        return "\n".join(lines) + "\n\n"
    if node.name == "table":
        return f"{node}\n\n"
    if node.name == "hr":
        return "---\n\n"
    if node.name in {"script", "style", "button", "svg", "iframe"}:
        return ""
    return "".join(block(child) if isinstance(child, Tag) else str(child) for child in node.children)


def markdown_from_article(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    article = soup.find("article") or soup.find(id="content_views")
    if not article:
        raise ValueError("No CSDN article content found")

    for node in article.select(
        "script, style, button, svg, iframe, .contentImg-no-view, .look-more-preCode, "
        ".pre-numbering, .opt-box"
    ):
        node.decompose()

    markdown = "".join(block(child) if isinstance(child, Tag) else str(child) for child in article.children)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = "\n".join(
        re.sub(r"^ +(?=\t)", "", line.rstrip()) for line in markdown.splitlines()
    ).strip() + "\n"
    return html.unescape(markdown)


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def front_matter(item: dict) -> str:
    lines = [
        "---",
        f"title: {yaml_quote(item['title'])}",
        f"date: {item['date']}",
        "draft: true",
        "tags:",
    ]
    lines.extend(f"  - {tag}" for tag in item.get("tags", []))
    lines.append("categories:")
    lines.extend(f"  - {category}" for category in item.get("categories", []))
    lines.append(f"source: {yaml_quote(item['source'])}")
    lines.append("---\n")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("content/posts"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    entries = json.loads(args.manifest.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for item in entries:
        output = args.output_dir / item["filename"]
        markdown_source = args.source_dir / f"{item['id']}.md"
        html_source = args.source_dir / f"{item['id']}.html"
        source = markdown_source if markdown_source.exists() else html_source
        if not source.exists():
            raise FileNotFoundError(source)
        if output.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {output}")
        content = source.read_text()
        if source.suffix == ".html":
            content = markdown_from_article(content)
        else:
            content = content.strip() + "\n"
        output.write_text(front_matter(item) + content)
        print(output)


if __name__ == "__main__":
    main()
