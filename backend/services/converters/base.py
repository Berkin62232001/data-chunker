from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ConversionOutput:
    markdown: str
    converter_used: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    fallback_used: bool = False


class BaseConverter(ABC):
    @abstractmethod
    def convert(self, file_path: Path) -> ConversionOutput:
        ...
