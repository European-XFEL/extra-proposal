import fnmatch
import glob
import logging
import os
import re
from datetime import datetime
from functools import wraps
from glob import iglob
from itertools import count, groupby
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .mymdc import MyMdcAccess

logger = logging.getLogger(__name__)


class ProposalNotFoundError(Exception):
    """
    Raised when the proposal is not found.
    """

    pass


def data_root_dir():
    return Path(os.environ.get('EXTRA_DATA_DATA_ROOT', '/gpfs/exfel/exp'))

# Copied from extra-data
def find_proposal(propno):
    for d in iglob(str(data_root_dir() / f'*/*/{propno}')):
        return Path(d)

    raise ProposalNotFoundError(f"Proposal {propno!r} was not found")


class RunReference:
    def __init__(self, proposal: 'Proposal', run_num: int):
        self.proposal = proposal
        self.run_num = run_num

    def data(self, **kwargs):
        """Open the data of this run with extra_data"""
        from extra_data import open_run
        return open_run(str(self.proposal.directory), self.run_num, **kwargs)

    def damnit(self):
        """Access DAMNIT results from this run through the damnit API"""
        return self.proposal.damnit()[self.run_num]

    def sample_name(self):
        """Get the sample name from myMdC for this run"""
        return self.proposal.run_sample_name(self.run_num)

    def run_type(self):
        """Get the run type from myMdC for this run"""
        return self.proposal.run_type(self.run_num)

    def plot_timeline(self):
        """Make a timeline of when this run was taken, migrated & calibrated"""
        import matplotlib.pyplot as plt

        run_info = self.proposal._run_info(self.run_num)
        cal_requests = run_info["cal_num_requests"]
        event_names = {
            "Run begin": "begin_at",
            "Run end": "end_at",
            "Migration requested": "migration_request_at",
            "Migration begin": "migration_begin_at",
            "Migration end": "migration_end_at",
            "Cal begin": "cal_last_begin_at",
            "Cal end": "cal_last_end_at"
        }

        events = dict()
        for name, key in event_names.items():
            if run_info[key] is not None:
                events[name] = datetime.fromisoformat(run_info[key])

        times = dict()
        if "Run end" in events and "Run begin" in events:
            times["Run"] = events["Run end"] - events["Run begin"]
        if "Migration end" in events and "Migration begin" in events:
            times["Migration"] = events["Migration end"] - events["Migration begin"]
        if "Cal end" in events and "Cal begin" in events:
            key = "Calibration" if cal_requests == 1 else f"Calibration attempt {cal_requests}"
            times[key] = events["Cal end"] - events["Cal begin"]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5))
        for (event, x) in events.items():
            if not (event.startswith("Cal") and cal_requests > 1):
                ax1.scatter(x, 1, label=event)

        ax1.legend(bbox_to_anchor=(1.01, 1.05))
        ax1.tick_params(left=False, labelleft=False)
        ax1.set_title("Timeline of run events")
        ax1.grid(axis="x")

        ax2.bar(times.keys(), [x.total_seconds() / 60 for x in times.values()])
        ax2.set_ylabel("Time [minutes]")
        ax2.set_title("Time taken in each state")
        ax2.grid(axis="y")

        fig.suptitle(f"p{self.proposal.number}, r{self.run_num} - {self.run_type()} - {self.sample_name()}")

        fig.tight_layout()

        return ax1

def _cache_by_run(func):
    @wraps(func)
    def wrapper(self: 'Proposal', run):
        key = (run, func.__name__)
        if key in self._cached_data:
            return self._cached_data[key]

        value = func(self, run)
        self._cached_data[key] = value

        return value

    return wrapper


class Proposal:
    def __init__(
        self,
        proposal: int | str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        user_email: Optional[str] = None,
        timeout=10,
    ):
        """Proposal object.
        It can be instantiated as Proposal(2112) or Proposal("p002112")

        Args:
            proposal (int | str): Proposal number.
            user_id (Optional[str], optional): UID (can be generated at https://in.xfel.eu/metadata/oauth/applications). Defaults to None.
            user_secret (Optional[str], optional): Secret (can be generated at https://in.xfel.eu/metadata/oauth/applications). Defaults to None.
            user_email (Optional[str], optional): User's email. Defaults to None.

        Raises:
            ProposalNotFoundError: The proposal does not exist.
        """
        # proposal ID and number
        if isinstance(proposal, str):
            if proposal[0] == "p":
                proposal = proposal[1:]

            self.number = int(proposal)
            self.directory_name = "p{:06d}".format(self.number)
        else:
            self.number = proposal
            self.directory_name = "p{:06d}".format(proposal)

        # is there a proposal with this ID?
        self.directory = find_proposal(self.directory_name).absolute()

        logger.info("Found proposal {}.".format(self.directory_name))

        if user_id is not None:
            self._mymdc = MyMdcAccess.oauth(
                client_id=user_id, client_secret=user_secret, user_email=user_email,
            )
        else:
            self._mymdc = MyMdcAccess.zwop(self.number)

        self._cached_data = {}
        self._timeout = 10

    def __repr__(self):
        return f"Proposal({self.number})"

    def __getitem__(self, run) -> RunReference:
        return RunReference(self, run)  # TODO: check that run exists?

    def damnit(self):
        """Access DAMNIT results from this proposal through the damnit API"""
        if 'damnit' in self._cached_data:
            return self._cached_data['damnit']

        from damnit import Damnit  # Optional dependency
        dmnt = self._cached_data['damnit'] = Damnit(self.number)
        return dmnt

    def _get_runs_filesystem(self) -> list[int]:
        """List runs available in RAW.

        Returns:
            list[int]: List of runs.
        """
        _runs_filesystem = sorted(
            [
                int(di.split("/")[-1][1:])
                for di in glob.glob("{}/raw/r????".format(self.directory))
            ]
        )
        return _runs_filesystem

    def _by_number_api_url(self, suffix=""):
        return f"proposals/by_number/{self.number}{suffix}"

    def _mymdc_info(self):
        if 'mymdc_info' in self._cached_data:
            return self._cached_data['mymdc_info']

        inf = self._mymdc.get(self._by_number_api_url())
        self._cached_data['mymdc_info'] = inf
        return inf

    def _get_runs_mymdc(self) -> list:
        return self._mymdc.get(self._by_number_api_url("/runs"))["runs"]

    def title(self):
        """Get the proposal title from myMdC"""
        return self._mymdc_info()["title"]

    def runs(self) -> list[int]:
        """Runs available in RAW.

        Returns:
            list[int]: List of runs.
        """
        return self._get_runs_filesystem()


    @_cache_by_run
    def _run_info(self, run: int) -> dict[str, Any]:
        data = self._mymdc.get(self._by_number_api_url("/runs/{run}"),
                                   timeout=self._timeout)
        if len(data["runs"]) == 0:
            raise RuntimeError(f"Couldn't get run information from mymdc for p{self.number}, r{run}")

        return data["runs"][0]

    @_cache_by_run
    def run_techniques(self, run: int) -> dict[str, Any]:
        run_info = self._run_info(run)
        data = self._mymdc.get(f'runs/{run_info["id"]}', timeout=self._timeout)
        return data['techniques']

    @_cache_by_run
    def run_sample_name(self, run: int) -> str:
        run_info = self._run_info(run)
        sample_id = run_info["sample_id"]
        data = self._mymdc.get(f"samples/{sample_id}", timeout=self._timeout)
        return data["name"]

    @_cache_by_run
    def run_type(self, run: int) -> str:
        run_info = self._run_info(run)
        experiment_id = run_info["experiment_id"]
        data = self._mymdc.get(f"experiments/{experiment_id}",
                                       timeout=self._timeout)

        return data["name"]

    def _get_samples_mymdc(self) -> list:
        prop_id = self._mymdc_info()["id"]
        return self._mymdc.get("samples", params={"proposal_id": prop_id})

    def samples_table(self):
        import pandas as pd
        runs_metadata = self._get_runs_mymdc()

        name, index, url, description, runs = [], [], [], [], []
        for si in self._get_samples_mymdc():
            _runs = []
            for ri in runs_metadata:
                if ri["sample_id"] == si["id"]:
                    _runs.append(ri["run_number"])

            name.append(si["name"])
            index.append(si["id"])
            url.append(si["url"])
            description.append(si["description"])
            runs.append(_runs)

        return pd.DataFrame.from_dict(
            {
                "name": name,
                "id": index,
                "url": url,
                "description": description,
                "runs": runs,
            }
        )

    @property
    def instrument(self):
        return self.directory.relative_to(data_root_dir()).parts[0]

    def info(self):
        """Display information on a given proposal."""

        # runs available in myMdC, and other information

        def run_ranges(sequence):
            # Adapted from:
            #  https://stackoverflow.com/questions/3429510/pythonic-way-to-convert-a-list-of-integers-into-a-string-of-comma-separated-rang

            # relevant to DAMNIT
            sequence = np.unique(sequence)

            grouped_sequence = (
                list(x) for _, x in groupby(sequence, lambda x, c=count(): next(c) - x)
            )
            return (
                ",".join(
                    "-".join(map(str, (gi[0], gi[-1])[: len(gi)]))
                    for gi in grouped_sequence
                ),
                sequence.size,
            )

        print(f"Proposal {self.number} ── scientific instrument {self.instrument}")
        print(f"Data stored at {self.directory}")

        # title
        if self.title() is not None:
            print(f"'{self.title()}'")

        # runs
        runs = self.runs()
        print("\nRuns collected: {} (total {})".format(*run_ranges(runs)))
        if self.damnit() is not None:
            grouped_sequence, size = run_ranges(self.damnit().runs())
            print(
                " └── {:.1f}% processed by DAMNIT".format(100 * size / len(runs)),
                end="",
            )
            if size != len(runs):
                print(": {} (total {})".format(grouped_sequence, size))
            else:
                print(".")

    def search_source(
        self, pattern: str, run: int | list[int] | None = None
    ) -> dict[int, list[str]]:
        """Perform a case insensitive search of the glob pattern in all data sources and aliases.

        Args:
            pattern (str): A glob-style pattern
            run (Optional[int  |  list[int]], optional): Specific run or list of runs. Defaults to None.

        Returns:
            dict[int, list[str]]: A dictionary of runs, and for each a list of
            strings matching the regular expression.

        Example:
            proposal = Proposal(1234)

            proposal.search_sources("*ENERGY*", run=[43, 44, 45, 46])
        """

        # TODO: look into aliases

        if run is None:
            run_list = self.runs()
        elif type(run) is int:
            run_list = [run]
        elif type(run) is list:
            run_list = run
            if not all(type(i) is int for i in run):
                raise TypeError("Each entry in the list must be an integer (run number)")
        else:
            raise TypeError(f"{type(run)} is not supported")

        source_re = re.compile(fnmatch.translate(pattern))

        run_match = {}
        for ri in run_list:
            run_match[ri] = []
            for si in self[ri].data().all_sources:
                if source_re.match(si):
                    run_match[ri].append(si)

        return run_match


if __name__ == "__main__":
    proposal = Proposal(5686)
    proposal.info()
    print("Run 42 sample:", proposal[42].sample_name())
