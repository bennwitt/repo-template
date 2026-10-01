from importlib.metadata import version

import repo_template


def test_version_matches_package_metadata() -> None:
    assert repo_template.__version__ == version("repo-template")
