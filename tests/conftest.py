from pathlib import Path  # noqa

from osgeo import gdal  # fix of fireatlas breaking links
import geopandas as gpd
import pytest

from hyp3_akfire_safe import gather as gl


gdal.UseExceptions()


@pytest.fixture(scope='session')
def scene_name():
    return 'LC09_L1GT_153230_20250928_20250928_02_T2'


@pytest.fixture(scope='session')
def geo_path():
    return Path(__file__).parent / 'data' / 'VX003XXX.A0000000.0000.000.0000000000000.nc'


@pytest.fixture(scope='session')
def aoi_db():
    return Path(__file__).parent / 'data' / 'AlaskaFireHistory_Polygons_AKAlbersNAD83_geojson_24_25.geojson'


@pytest.fixture(scope='session')
def points_db():
    return Path(__file__).parent / 'data' / 'AlaskaFireHistory_Points_NAD83_geojson_24_25.geojson'


def test_data_directory():
    here = Path(Path(__file__).parent)
    return here / 'data'


@pytest.fixture(scope='session')
def test_intersection(aoi_db) -> gpd.GeoDataFrame:
    scene_name = 'LC09_L1GT_153230_20250928_20250928_02_T2'
    metadata, stac_gdf = gl.find_landsat_s2(scene_name)
    points_db = Path(__file__).parent / 'data' / 'AlaskaFireHistory_Points_NAD83_geojson_24_25.geojson'
    fireseason = 2025
    intersection = gl.find_intersection(stac_gdf, Path(aoi_db), Path(points_db), fireseason)

    return intersection
