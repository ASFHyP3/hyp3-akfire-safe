"""Plugin with workflows for akfire-safe."""

from importlib.metadata import version

# this import is meant to fix the sklearn bindings for fireatlas
import sklearn  # noqa


__version__ = version(__name__)

__all__ = [
    '__version__',
]
