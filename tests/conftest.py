import yaml
import pytest

from extra_data.tests.mockdata import write_file
from extra_data.tests.mockdata.xgm import XGM


@pytest.fixture
def proposal_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRA_DATA_DATA_ROOT", str(tmp_path))

    proposal_dir = tmp_path / "MID" / "202501" / "p008034"
    proposal_dir.mkdir(parents=True)

    (proposal_dir / "raw" / "r0001").mkdir(parents=True)
    (proposal_dir / "raw" / "r0002").mkdir(parents=True)

    yield proposal_dir


@pytest.fixture
def mymdc_credentials(proposal_dir):
    path = proposal_dir / "usr" / "mymdc-credentials.yml"
    path.parent.mkdir()
    with open(path, "w") as f:
        yaml.dump({
            "token": "foo",
            "server": "https://out.xfel.eu/metadata"
        }, f)

    yield path


@pytest.fixture
def proposal_with_run(proposal_dir):
    run_dir = proposal_dir / "raw" / "r0001"
    write_file(run_dir / "RAW-R0001-DA01-S00000.h5", [
        XGM("SA2_XTD1_XGM/XGM/DOOCS"),
    ], ntrains=10)

    aliases_path = proposal_dir / "usr" / "extra-data-aliases.yml"
    aliases_path.parent.mkdir()
    aliases_path.write_text("xgm: SA2_XTD1_XGM/XGM/DOOCS")

    yield proposal_dir
