import json
from abc import ABC, abstractmethod
from pathlib import Path


class Storage(ABC):
    """Interface abstraite de stockage."""

    @abstractmethod
    def load(self) -> dict:
        pass

    @abstractmethod
    def save(self, data: dict) -> None:
        pass


class JsonStorage(Storage):
    """Stockage sur fichier JSON."""

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)

    def load(self) -> dict:
        if not self.filepath.exists():
            raise FileNotFoundError(f"Data file not found at '{self.filepath}'.")
        with open(self.filepath, encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: dict) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class MemoryStorage(Storage):
    """Stockage en mémoire (pour les tests)."""

    def __init__(self, initial_data: dict | None = None):
        self._data = initial_data or {}

    def load(self) -> dict:
        return self._data

    def save(self, data: dict) -> None:
        self._data = data
