# Experimental v0.1.0 validation

The core release checks passed locally on Windows with Python 3.11. The self-contained
demo also ran through all eight stages as real subprocesses and produced its ZIP bundle.

```sh
python -m unittest discover -s tests -p test_smoke_unittest.py -v
```

The 13 core checks cover the complete demo, three human gates, single-use approvals,
changed evidence/configuration/workspace, preserved prior run reports, invalid
configuration, invalid resume points, duplicate claims, concurrent history writes,
retry limits, stage failure routing, and CLI failure status.

All Python source files were parsed for syntax errors. The release patch was checked
against the supplied snapshot, whose original blob hashes matched public main commit
`9c0d628e04418f096f37f9e37353d13baca4cee2`.

## Completed release verification

Dependencies were installed from `requirements.txt` into an isolated virtual environment
on Windows with Python 3.13. The complete test suite, including the Flask route tests,
passed:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
```

Result: **144 passed**. The Flask application imported successfully with its full route
map, all Python sources compiled successfully, and the 13 core checks above passed again.
The included GitHub Actions workflow runs the same pytest check on Windows and Linux with
Python 3.10 and 3.12.

The release branch and pull request are prepared separately from this validation record.
No release tag or blog change is part of this release-preparation step.
