from pathlib import Path
import pytest
from src.alerts import PROPERTIES, read_alerts

ALERTS = Path(__file__).resolve().parents[1] / "outputs" / "real" / "alerts.geojson"

pytestmark = pytest.mark.skipif(not ALERTS.exists(), reason="run python -m src.real_pipeline first")


@pytest.fixture(scope="module")
def features():
    return read_alerts(ALERTS)["features"]


def test_not_empty(features):
    assert len(features) > 0


def test_required_fields_on_every_feature(features):
    for f in features:
        missing = [k for k in PROPERTIES if k not in f["properties"]]
        assert not missing, f"{f['properties'].get('asset_id')} missing {missing}"


def test_ranks_are_unique(features):
    ranks = [f["properties"]["rank"] for f in features]
    assert len(ranks) == len(set(ranks))


def test_scores_between_0_and_100(features):
    for f in features:
        assert 0 <= f["properties"]["risk_score"] <= 100


def test_asset_ids_are_unique(features):
    ids = [f["properties"]["asset_id"] for f in features]
    assert len(ids) == len(set(ids))


def test_every_feature_has_geometry(features):
    assert all(f["geometry"] for f in features)


def test_metadata_matches_feature_count():
    meta = read_alerts(ALERTS)["metadata"]
    assert meta["feature_count"] == len(read_alerts(ALERTS)["features"])