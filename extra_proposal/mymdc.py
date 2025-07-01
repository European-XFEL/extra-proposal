import json
import os
from glob import iglob
from pathlib import Path
from urllib.parse import urljoin

import yaml
import requests
from oauth2_xfel_client import Oauth2ClientBackend

MYMDC_BASE_URL = "https://in.xfel.eu/metadata"
ZWOP_BASE_URL  = "https://exfldadev01.desy.de/zwop"

# Copied from extra-data
def find_proposal(propno):
    root_dir = Path(os.environ.get('EXTRA_DATA_DATA_ROOT', '/gpfs/exfel/exp'))
    for d in iglob(str(root_dir / f'*/*/{propno}')):
        return Path(d)

    raise Exception(f"Couldn't find proposal dir for {propno!r}")


class MyMdcAccess:
    _oauth_cache = {}  # Keyed by client ID

    def __init__(self, base_api_url: str, auth_headers, oauth_client=None):
        self.base_api_url = base_api_url.rstrip("/") + "/"  # Ensure trailing /
        self.auth_headers = auth_headers.copy()
        self.oauth_client = oauth_client
        if oauth_client is not None:
            self.session = self.oauth_client.session
        else:
            self.session = requests.Session()

    @classmethod
    def oauth(cls, client_id, client_secret, user_email):
        if client_id in cls._oauth_cache:
            return cls._oauth_cache[client_id]

        oauth_client = Oauth2ClientBackend(
            client_id=client_id,
            client_secret=client_secret,
            scope="",
            token_url=f"{MYMDC_BASE_URL}/oauth/token"
        )
        inst = cls(f"{MYMDC_BASE_URL}/api", {"X-User-Email": user_email}, oauth_client)
        cls._oauth_cache[client_id] = inst
        return inst

    @classmethod
    def zwop(cls, proposal, timeout=10):
        proposal_path = find_proposal(f"p{proposal:06d}")
        credentials_path = proposal_path / "usr/mymdc-credentials.yml"
        if not credentials_path.is_file():
            params = {
                "proposal_no": str(proposal),
                "kinds": "mymdc",
                "overwrite": "false",
                "dry_run": "false"
            }
            response = requests.post(
                f"{ZWOP_BASE_URL}/api/write_tokens", params=params, timeout=timeout
            )
            response.raise_for_status()

        with open(credentials_path) as f:
            document = yaml.safe_load(f)
            token = document["token"]
            server = document["server"]

        return cls(f"{server}/api/mymdc", {"X-API-key": token})

    def default_headers(self):
        from . import __version__
        return {
            "content-type": "application/json",
            "Accept": "application/json; version=1",
            "User-Agent": f"EXtra-proposal/{__version__}",
        } | self.auth_headers

    def get_request(self, relative_url, params=None, headers=None, **kwargs):
        """Make a GET request, return the HTTP response object"""
        # Base URL may include e.g. '/api/'. This is a prefix for all URLs;
        # even if they look like an absolute path.
        url = urljoin(self.base_api_url, relative_url.lstrip("/"))
        headers = self.default_headers() | (headers or {})
        return self.session.get(url, params=params, headers=headers, **kwargs)

    @staticmethod
    def _parse_response(resp: requests.Response):
        if resp.status_code >= 400:
            try:
                d = json.loads(resp.content.decode("utf-8"))
            except Exception:
                resp.raise_for_status()
            else:  # Add the error message from the API
                raise requests.HTTPError(
                    f"Error {resp.status_code} from API: "
                    f"{d.get('info', 'missing details')}",
                    response=resp,
                )

        if resp.content == b"":
            return None
        else:
            return resp.json()

    def get(self, relative_url, params=None, **kwargs):
        """Make a GET request, return response content from JSON"""
        resp = self.get_request(relative_url, params, **kwargs)
        return self._parse_response(resp)
