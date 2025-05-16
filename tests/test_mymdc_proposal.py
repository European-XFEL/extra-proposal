from datetime import datetime
from unittest.mock import MagicMock, patch

import requests
import matplotlib.pyplot as plt
from extra_mymdc import MyMdcProposal


# Helper function to mock requests.get() for different endpoints
def mock_get(url, headers, timeout):
    assert headers["X-API-key"] == "foo"

    if "proposals/by_number" in url:
        dt = datetime.now().isoformat()

        result = dict(runs=[dict(id=1,
                                 sample_id=1,
                                 experiment_id=1,
                                 cal_num_requests=1,
                                 begin_at=dt,
                                 end_at=dt,
                                 migration_request_at=dt,
                                 migration_begin_at=dt,
                                 migration_end_at=dt,
                                 cal_last_begin_at=dt,
                                 cal_last_end_at=dt)])
    elif "samples" in url:
        result = dict(name="mithril")
    elif "experiments" in url:
        result = dict(name="alchemy")
    elif "/runs/" in url:
        result = {'techniques': [
            {'identifier': 'PaNET01168', 'name': 'SFX'},
            {'identifier': 'PaNET01188', 'name': 'SAXS'},
        ]}

    response = MagicMock()
    response.json.return_value = result
    return response


def test_mymdc_proposal(mymdc_credentials):
    mymdc = MyMdcProposal(8034)

    with patch.object(requests, "get", side_effect=mock_get):
        assert mymdc.run_sample_name(1) == "mithril"
        assert len(mymdc.run_techniques(1)) == 2
        assert mymdc.run_type(1) == "alchemy"

        # Smoke test
        assert isinstance(mymdc.plot_run(1), plt.Axes)

    assert repr(mymdc) == "MyMdcProposal(8034)"
