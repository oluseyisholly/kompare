"""Parse Cardtonic's article without inventing limits absent from the source."""
import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_kyc_article(soup: BeautifulSoup) -> dict:
    article = soup.select_one("article")
    title = soup.select_one("h1")
    if article is None or title is None:
        raise ValueError("Cardtonic KYC article or title is missing")
    for section in article.find_all("section"):
        if section.find("a", href=re.compile(r"/articles/")):
            section.decompose()
    levels = []
    for heading in article.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(" ", strip=True).rstrip(":")
        if name.lower() not in {"basic kyc", "advanced kyc"}:
            continue
        requirements, notes, content = [], [], []
        for node in heading.find_all_next(["h2", "h3", "h4", "p", "li"]):
            if article not in node.parents or node.name in {"h2", "h3", "h4"}:
                break
            if node.name == "p" and node.find_parent("li"):
                continue
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            content.append(text)
            if text.lower().startswith("tap "):
                continue
            if node.name == "li" or text.lower().startswith("upload "):
                requirements.append(re.split(r"\s+Tap\s+", text, maxsplit=1)[0])
            else:
                notes.append(text)
        if not requirements:
            raise ValueError(f"No requirements found for Cardtonic {name}")
        levels.append({"level_name": name, "description": "\n".join(content),
                       "requirements": requirements, "notes": "\n".join(notes),
                       "metadata_json": {"limits_published": False}})
    if {level["level_name"].lower() for level in levels} != {"basic kyc", "advanced kyc"}:
        raise ValueError("Expected Basic and Advanced Cardtonic KYC sections")
    timestamp = soup.select_one("time[datetime]")
    updated_at = None
    if timestamp:
        try:
            updated_at = datetime.fromisoformat(timestamp["datetime"].replace("Z", "+00:00"))
        except ValueError:
            pass
    return {"title": title.get_text(" ", strip=True), "updated_at": updated_at,
            "content": article.get_text("\n", strip=True), "levels": levels}
