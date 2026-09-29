import importlib.util
from pathlib import Path

import pytest


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0043_six_digit_product_barcodes.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0043", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_product_mapping_is_sequential_and_bounded():
    migration = _migration_module()
    assert migration.barcode_for_position(1) == "100001"
    assert migration.barcode_for_position(2) == "100002"
    assert migration.barcode_for_position(migration.BARCODE_CAPACITY) == "999999"
    with pytest.raises(ValueError, match="exhausted"):
        migration.barcode_for_position(migration.BARCODE_CAPACITY + 1)
