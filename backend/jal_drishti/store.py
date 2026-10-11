import threading
from pathlib import Path
from typing import Optional, Union

from .config import resolve_data_dir
from .data_loader import load_dataset
from .models import Dataset


class DataStore:
    """Loads the CSVs lazily, once. A failed load is retried on the next request (fix the file, no restart)."""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        self.data_dir: Path = resolve_data_dir(data_dir)
        self._dataset: Optional[Dataset] = None
        self._lock = threading.Lock()

    def get(self) -> Dataset:
        ds = self._dataset
        if ds is not None:
            return ds
        with self._lock:
            if self._dataset is None:
                self._dataset = load_dataset(self.data_dir)
            return self._dataset

    def reload(self) -> Dataset:
        with self._lock:
            self._dataset = None
        return self.get()
