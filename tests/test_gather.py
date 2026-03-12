from pathlib import Path

import pytest

from hyp3_akfire_safe import gather as gl


def test_get_lc2_path():
    metadata = {'id': 'L--8', 'assets': {'green': {'href': 'foo'}}}
    assert gl.get_lc2_path(metadata, band=3) == 'foo'

    metadata = {'id': 'L--8', 'assets': {'B8.TIF': {'href': 'foo'}}}
    assert gl.get_lc2_path(metadata, band=8) == 'foo'

    metadata = {'id': 'L--8', 'assets': {'pan': {'href': 'foo'}}}
    assert gl.get_lc2_path(metadata, band=8) == 'foo'

    with pytest.raises(ValueError):
        gl.get_lc2_path(metadata, band=0)

    metadata = {'id': 'L--4', 'assets': {'fake': {'href': 'foo'}}}
    with pytest.raises(NotImplementedError):
        gl.get_lc2_path(metadata, band=1)


def test_find_scene(scene_name):
    metadata, gdf = gl.find_landsat(scene_name)

    assert metadata['id'] == scene_name

    assert not gdf.empty

    new_scene = 'LC00_L1GT_000000_00000000_00000000_00_T0'
    with pytest.raises(RuntimeError):
        gl.find_landsat(new_scene)


def test_geo_viirs_intersects(geo_path):
    assert gl.geo_viirs_intersects(geo_path, (-1, -1, 1, 1))


def test_find_intersection(scene_name, aoi_db, points_db, test_intersection):
    metadata, stac = gl.find_landsat(scene_name)
    intersection = test_intersection
    assert not intersection.empty

    with pytest.raises(RuntimeError):
        gl.find_intersection(stac, Path(aoi_db), Path(points_db), fireseason=2026)
