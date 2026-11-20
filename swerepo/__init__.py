"""SWERepo: set up a repository the way an AI-assisted team should work, and keep it that way."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("swerepo")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"
