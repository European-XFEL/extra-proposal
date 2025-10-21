# EXtra-proposal

A small Python library to work with European XFEL proposals: list runs, read
metadata from MyMDC, open data with EXtra-data, access DAMNIT results, and make
simple run timelines.

## Install

EXtra-proposal is available in our Python environment on the Maxwell cluster:

```shell
module load exfel exfel-python
```

You can also install it from [from
PyPI](https://pypi.org/project/extra-proposal/) to use in other environments
with Python 3.9+:

```shell
pip install extra-proposal

# Optional extras, installs: extra-data, damnit, pandas
pip install "extra-proposal[extra]"   
```

## Quick start

```python
from extra_proposal import Proposal

# Create a proposal object
prop = Proposal(1234)

print(prop.title())    # Proposal Title from MyMDC
print(prop.runs())     # List runs found in /raw on disk

# Per-run helpers
print(prop[1].sample_name())
print(prop.run_type(1))
print(prop.run_techniques(1))

# Open data (requires EXtra-data)
run = prop[1].data()
# Open DAMNIT results (required damnit)
damnit = prop[1].damnit()

# Plot a simple timeline
prop[1].plot_timeline()
```

## Environment and auth

By default MyMDC data is accessed using Zwop credentials stored under the
proposal at `usr/mymdc-credentials.yml` (created automatically when available).
It is possible to use your MyMdc
[Oauth](https://in.xfel.eu/metadata/oauth/applications) credentials instead, in
case ZWOP isn't available or the metadata endpoint isn't accessible through
Zwop:

```python
Proposal(8034, user_id="...", user_secret="...", user_email="...")
```
