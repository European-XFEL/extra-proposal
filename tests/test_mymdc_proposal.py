from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests
import matplotlib.pyplot as plt

from extra_proposal import Proposal
from extra_proposal.proposal import ProposalNotFoundError


# Helper function to mock requests.get() for different endpoints
def mock_get(url, *, headers, **kwargs):
    assert headers["X-API-key"] == "foo"

    if "proposals/by_number" in url:
        dt = datetime.now().isoformat()

        result = dict(
            runs=[dict(id=1,
                       sample_id=1,
                       experiment_id=1,
                       cal_num_requests=1,
                       begin_at=dt,
                       end_at=dt,
                       migration_request_at=dt,
                       migration_begin_at=dt,
                       migration_end_at=dt,
                       cal_last_begin_at=dt,
                       cal_last_end_at=dt)],
            title="Test Proposal",
            id=1234,
        )
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
    response.status_code = 200
    return response


def test_mymdc_proposal_online(mymdc_credentials):
    # Test normal operation when MyMdC is available
    prop = Proposal(8034)

    with patch.object(prop._mymdc.session, "get", side_effect=mock_get):
        assert prop.run_sample_name(1) == "mithril"
        assert len(prop.run_techniques(1)) == 2
        assert prop.run_type(1) == "alchemy"

        # Smoke test
        assert isinstance(prop[1].plot_timeline(), plt.Axes)

    assert repr(prop) == "Proposal(8034)"


def test_damnit_availability(mymdc_credentials):
    prop = Proposal(8034)
    mock_damnit_instance = MagicMock()

    with patch('damnit.Damnit') as mock_damnit:
        mock_damnit.return_value = mock_damnit_instance

        # First call should instantiate Damnit and return the instance
        res1 = prop.damnit()
        mock_damnit.assert_called_once_with(8034)
        assert res1 is mock_damnit_instance

        # Second call should return the cached instance
        res2 = prop.damnit()
        mock_damnit.assert_called_once()  # Not called again
        assert res2 is mock_damnit_instance


    prop = Proposal(8034)

    with patch('damnit.Damnit') as mock_damnit:
        mock_damnit.side_effect = FileNotFoundError

        with pytest.raises(FileNotFoundError):
            prop.damnit()

        # Second call should fail again
        with pytest.raises(FileNotFoundError):
            prop.damnit()

        # smoke test: Proposal.info() still works
        with patch.object(prop._mymdc.session, "get", side_effect=mock_get):
            prop.info()


def test_proposal_lazy_mymdc_connection(proposal_dir):
    # Test that Proposal can be instantiated when MyMdC is down

    # simulate ZWOP server being down
    with patch("extra_proposal.mymdc.requests.post") as mock_post:
        mock_post.side_effect = requests.ConnectionError("ZWOP server is down")

        # Instantiation succeed
        prop = Proposal(8034)
        assert repr(prop) == "Proposal(8034)"

        # Methods not using MyMdc work
        assert prop.instrument == "MID"
        assert prop.runs() == [1, 2]

        # Methods using MyMdc should now fail when called
        with pytest.raises(requests.ConnectionError, match="ZWOP server is down"):
            prop.title()

        with pytest.raises(requests.ConnectionError, match="ZWOP server is down"):
            prop.run_sample_name(1)


def test_proposal_not_found(proposal_dir):
    with pytest.raises(ProposalNotFoundError):
        Proposal(1234)
