"""
Local python-for-android recipe for reportlab.

Overrides p4a's built-in reportlab recipe (which pins reportlab 3.x and
tries to compile the _rl_accel C extension — broken on Python 3.11+).

reportlab 4.x is pure Python: no C extension, nothing to compile.
"""
from pythonforandroid.recipe import PythonRecipe


class ReportLabRecipe(PythonRecipe):
    version = "4.2.5"
    url = "https://pypi.python.org/packages/source/r/reportlab/reportlab-{version}.tar.gz"
    depends = ["python3", "setuptools", "pillow", "charset-normalizer"]
    site_packages_name = "reportlab"
    call_hostpython_via_targetpython = False


recipe = ReportLabRecipe()
