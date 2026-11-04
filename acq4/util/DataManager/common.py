import os


def abspath(fileName):
    """Return an absolute path string which is guaranteed to uniquely identify a file."""
    return os.path.normcase(os.path.abspath(fileName))


def casepath(fileName):
    """Return the absolute path of *fileName* with the capitalization it has on disk.

    abspath() lowercases on Windows so it can be used as a lookup key; use this for paths that are
    shown to users or used to create files. Only the capitalization is taken from the filesystem:
    if resolving the path would also rewrite it (symlinks, junctions, mapped drives), the path is
    returned unchanged.
    """
    path = os.path.abspath(fileName)
    if os.name != 'nt':
        return path
    try:
        real = os.path.realpath(path)
    except OSError:
        return path
    return real if os.path.normcase(real) == os.path.normcase(path) else path
