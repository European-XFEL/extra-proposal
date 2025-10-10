import os
from pathlib import Path

class ProposalNotFoundError(Exception):
    """
    Raised when the proposal is not found.
    """
    pass


def data_root_dir():
    return Path(os.environ.get('EXTRA_DATA_DATA_ROOT', '/gpfs/exfel/exp'))


# Copied from extra-data
def find_proposal(propno):
    for d in data_root_dir().glob(f'*/*/{propno}'):
        return d

    raise ProposalNotFoundError(f"Proposal {propno!r} was not found")
