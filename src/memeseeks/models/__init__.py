"""The model wrappers.

Importing any of them turns off transformers' background safetensors conversion: for a repo that only has
pytorch_model.bin (both default models), it would download the whole model a second time from a
conversion pull request, doubling the first run's download to about 8 GB.
"""

import os

os.environ.setdefault("DISABLE_SAFETENSORS_CONVERSION", "true")
