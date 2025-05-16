import yaml
import pytest

@pytest.fixture
def mymdc_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRA_DATA_DATA_ROOT", str(tmp_path))

    proposal_dir = tmp_path / "MID" / "202501" / "p008034"
    proposal_dir.mkdir(parents=True)

    path = proposal_dir / "usr" / "mymdc-credentials.yml"
    path.parent.mkdir()
    with open(path, "w") as f:
        yaml.dump({
            "token": "foo",
            "server": "https://out.xfel.eu/metadata"
        }, f)

    yield path
