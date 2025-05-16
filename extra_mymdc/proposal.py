import os
from typing import Any
from glob import iglob
from pathlib import Path
from functools import wraps
from datetime import datetime

import yaml
import requests


# Copied from extra-data
def find_proposal(propno):
    root_dir = Path(os.environ.get('EXTRA_DATA_DATA_ROOT', '/gpfs/exfel/exp'))
    for d in iglob(str(root_dir / f'*/*/{propno}')):
        return Path(d)

    raise Exception(f"Couldn't find proposal dir for {propno!r}")


class MyMdcProposal:
    def __init__(self, proposal, timeout=10, init_server="https://exfldadev01.desy.de/zwop", enable_cache=True):
        self._proposal = proposal
        self._timeout = timeout
        self._enable_cache = enable_cache
        self._cached_data = {}

        proposal_path = find_proposal(f"p{proposal:06d}")
        credentials_path = proposal_path / "usr/mymdc-credentials.yml"
        if not credentials_path.is_file():
            params = {
                "proposal_no": str(proposal),
                "kinds": "mymdc",
                "overwrite": "false",
                "dry_run": "false"
            }
            response = requests.post(f"{init_server}/api/write_tokens", params=params, timeout=timeout)
            response.raise_for_status()

        with open(credentials_path) as f:
            document = yaml.safe_load(f)
            token = document["token"]
            self._server = document["server"]

        self._headers = { "X-API-key": token }

    @property
    def proposal(self):
        return self._proposal

    def _cache(func):
        @wraps(func)
        def wrapper(self, run):
            key = (run, func.__name__)
            if self._enable_cache and key in self._cached_data:
                return self._cached_data[key]

            value = func(self, run)
            if self._enable_cache:
                self._cached_data[key] = value

            return value

        return wrapper

    @_cache
    def _run_info(self, run: int) -> dict[str, Any]:
        response = requests.get(f"{self._server}/api/mymdc/proposals/by_number/{self.proposal}/runs/{run}",
                                headers=self._headers, timeout=self._timeout)
        response.raise_for_status()
        json = response.json()
        if len(json["runs"]) == 0:
            raise RuntimeError(f"Couldn't get run information from mymdc for p{self.proposal}, r{run}")

        return json["runs"][0]

    @_cache
    def run_techniques(self, run: int) -> dict[str, Any]:
        run_info = self._run_info(run)
        response = requests.get(f'{self._server}/api/mymdc/runs/{run_info["id"]}',
                                headers=self._headers, timeout=self._timeout)
        response.raise_for_status()
        return response.json()['techniques']

    @_cache
    def run_sample_name(self, run: int) -> str:
        run_info = self._run_info(run)
        sample_id = run_info["sample_id"]
        response = requests.get(f"{self._server}/api/mymdc/samples/{sample_id}",
                                headers=self._headers, timeout=self._timeout)
        response.raise_for_status()

        return response.json()["name"]

    @_cache
    def run_type(self, run: int) -> str:
        run_info = self._run_info(run)
        experiment_id = run_info["experiment_id"]
        response = requests.get(f"{self._server}/api/mymdc/experiments/{experiment_id}",
                                headers=self._headers, timeout=self._timeout)
        response.raise_for_status()

        return response.json()["name"]

    def plot_run(self, run: int):
        import matplotlib.pyplot as plt

        run_info = self._run_info(run)
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

        fig.suptitle(f"p{self.proposal}, r{run} - {self.run_type(run)} - {self.run_sample_name(run)}")

        fig.tight_layout()

        return ax1

    def __repr__(self):
        return f"{type(self).__name__}({self.proposal})"
