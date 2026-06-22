"""Shared data model for collected papers."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Paper:
    source: str
    title: str
    authors: List[str]
    abstract: str
    url: str
    published_date: str
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "url": self.url,
            "published_date": self.published_date,
            "keywords": self.keywords,
        }
