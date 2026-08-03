"""Tests for the storage seam's real configuration.

The rest of the suite deliberately never touches the real storage root — the
`client` fixture monkeypatches it to a temp directory so tests stay hermetic.
That isolation is correct, but it means nothing else here can catch the root
itself being wrong, which is the blind spot this file exists to cover.
"""
from pathlib import Path

from infra import storage


def test_storage_root_is_at_the_backend_root():
    """STORAGE_ROOT is derived from storage.py's own __file__, so moving the
    module silently moves the data directory with it.

    That is exactly what happened when storage.py moved into infra/ during the
    package refactor: the root became backend/infra/storage while the
    (gitignored) data stayed at backend/storage, and every native clip, upload,
    analysis archive and alignment became invisible to the running app. The
    whole suite stayed green throughout, because it only ever used temp roots.

    Anchoring the expectation on this test file's location instead of on
    storage.py's means a future move of the module fails here rather than at
    runtime.
    """
    backend_root = Path(__file__).resolve().parent.parent
    assert storage.STORAGE_ROOT == backend_root / "storage"
