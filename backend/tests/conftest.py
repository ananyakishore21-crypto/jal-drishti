from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jal_drishti.api import create_app
from jal_drishti.data_loader import load_dataset

REPO_DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="session")
def real_data_dir():
    if not (REPO_DATA / "bhopal_ghats_2023_2025.csv").is_file():
        pytest.skip("real data files not present in ../data")
    return REPO_DATA


@pytest.fixture(scope="session")
def real_dataset(real_data_dir):
    return load_dataset(real_data_dir)


@pytest.fixture(scope="session")
def client(real_data_dir):
    return TestClient(create_app(real_data_dir))
