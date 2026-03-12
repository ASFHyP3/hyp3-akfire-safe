"""gather processing."""

import logging
import math
import os
from argparse import ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import earthaccess
import geopandas as gpd
import netCDF4
import numpy as np
import pandas as pd
import pystac_client
import rasterio
import utm
from hyp3lib.aws import get_content_type, get_tag_set
from osgeo import gdal
from pyresample import geometry, kd_tree
from rasterio.transform import from_bounds


gdal.UseExceptions()

LANDSAT_CATALOG_API = 'https://landsatlook.usgs.gov/stac-server'
LANDSAT_CATALOG = pystac_client.Client.open(LANDSAT_CATALOG_API)
LANDSAT_BUCKET = 'usgs-landsat'


log = logging.getLogger(__name__)


auth = earthaccess.login()

BUFFER = 1000  # Buffer zone 1000 meters


def get_lc2_path(metadata: dict, band: int) -> str:
    """Get Landsat link.

    Args:
        metadata: Dictionary from json file associated with the Landsat image.
        band: Band to extract.

    Returns:
        Bucket link for Landsat image.
    """
    bands = {1: 'coastal', 2: 'blue', 3: 'green', 4: 'red', 5: 'nir08', 6: 'swir16', 7: 'swir22', 8: 'pan'}
    if band > 8 or band < 1:
        raise ValueError(f'Band {band} is not valid, choose a value between 1 and 8')

    if metadata['id'][3] in ('8', '9'):
        tif = metadata['assets'].get(f'B{band}.TIF')
        if tif is None:
            tif = metadata['assets'][bands[band]]
    else:
        raise NotImplementedError(f'AK Fire Safe processing not available for this platform. {metadata["id"][:3]}')

    return tif['href'].replace('https://landsatlook.usgs.gov/data/', f'/vsis3/{LANDSAT_BUCKET}/')


def join_dataframes(aoi: Path, points: Path, crs: str) -> gpd.GeoDataFrame:
    """Join fire AOI and fire points databases by FIREID.

    Args:
        aoi: Path to AOI database.
        points: Path to points database.
        crs: EPSG code.

    Returns:
        gdf: Joined database.
    """
    gdf_aoi = gpd.read_file(str(aoi))
    gdf_points = gpd.read_file(str(points))
    gdf_points = gdf_points[['ID', 'DISCOVERYDATETIME']]
    gdf_aoi = gpd.GeoDataFrame(
        pd.merge(gdf_aoi, gdf_points, how='left', left_on='FIREID', right_on='ID'), geometry='geometry'
    )
    gdf_aoi = gdf_aoi.to_crs(crs)
    gdf_aoi['start_date'] = pd.to_datetime(gdf_aoi['DISCOVERYDATETIME'], unit='ms').dt.tz_localize(
        'America/Anchorage'
    ).dt.tz_convert('UTC') - pd.Timedelta(days=2)
    gdf_aoi['end_date'] = pd.to_datetime(gdf_aoi['FPOUTDATE'], unit='ms').dt.tz_localize(
        'America/Anchorage'
    ).dt.tz_convert('UTC') + pd.Timedelta(days=2)

    return gdf_aoi


def find_intersection(stac: gpd.GeoDataFrame, aoi: Path, points: Path, fireseason: int | None) -> gpd.GeoDataFrame:
    """Find intersection between landsat image and AOIs.

    Args:
        stac: DataFrame with image metadata.
        aoi: Path of database with AOIs.
        points: Path of database with fire points.
        fireseason: Year of the fire season.

    Returns:
        intersection: Dataframe with Polygons of the intersections.
    """
    gdf_aoi = join_dataframes(aoi, points, str(stac.crs))
    if fireseason is not None:
        gdf_aoi = gdf_aoi[gdf_aoi['FIREYEAR'] == str(fireseason)]
    inter = gpd.overlay(stac, gdf_aoi, how='intersection').to_crs(f'{stac["proj:code"][0]}')
    inter = inter[(inter['start_date'] <= inter['datetime']) & (inter['end_date'] >= inter['datetime'])]
    if inter.empty:
        raise RuntimeError(f'The scene {stac["id"][0]} does not overlap with any fires in {fireseason}')
    return inter


def clip_landsat(scene: Path, inter: gpd.GeoDataFrame) -> tuple[list[Path], list[str]]:
    """Clips the image using AOIs.

    Args:
        scene: Image file path.
        inter: GeoDataFrame with the AOIs.

    Returns:
        filepaths: File paths of the clipped images.
    """
    prefixes = []
    filenames = []
    ds = gdal.Open(scene.resolve(), gdal.GA_ReadOnly)
    print(inter['FIREYEAR'].iloc[0])
    for i, geom in enumerate(inter['geometry']):
        bbox = [geom.bounds[0] - BUFFER, geom.bounds[3] + BUFFER, geom.bounds[2] - BUFFER, geom.bounds[1] + BUFFER]
        platform = f'L{scene.name[3]}'
        prefix = Path(f'{inter["FIREYEAR"].iloc[i]}/{inter["FIREID"].iloc[i]}/{platform}/')
        filename = f'{inter["FIREID"].iloc[i]}_{inter["id"].iloc[i]}_{scene.name.split("_")[-1]}'
        filepath = prefix / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        out = gdal.Translate(filepath.resolve(), ds, projWin=bbox)
        del out
        prefixes.append(prefix)
        filenames.append(filename)

    return prefixes, filenames


def find_landsat(scene_name: str) -> tuple[dict, gpd.GeoDataFrame]:
    """Finds a Landsat image.

    Args:
        scene_name: Name of the scene.

    Returns:
        filename: Path of the downloaded image.
    """
    search = LANDSAT_CATALOG.search(ids=[scene_name])
    item_collection = search.item_collection()
    item_collection.save_object('my_stac_results.json')
    gdf = gpd.read_file('my_stac_results.json')
    Path('my_stac_results.json').unlink()
    items = list(search.items())
    if len(items) < 1:
        raise RuntimeError(f'The scene {scene_name} is not in the bucket')

    metadata = items[0].to_dict()

    return metadata, gdf


def download_landsat(metadata: dict, band: int) -> Path:
    """Downloads a Landsat image.

    Args:
        metadata: Dictionary with the scene metadata.
        band: Band to extract.

    Returns:
        filename: Path of the downloaded image.
    """
    os.environ['AWS_REGION'] = 'us-west-2'
    os.environ['AWS_REQUEST_PAYER'] = 'requester'
    gdal.SetConfigOption('AWS_REGION', 'us-west-2')
    gdal.SetConfigOption('AWS_REQUEST_PAYER', 'requester')
    url = get_lc2_path(metadata, band)
    filename = url.split('/')[-1]
    gdal.Translate(filename, url)
    return Path(filename)


def upload_file_to_s3_with_publish_access_keys(
    path_to_file: Path, bucket: str, prefix: str = '', s3_name: str | None = None
) -> None:
    """Uploads file to s3 bucket.

    Args:
        path_to_file: Path to tif file.
        bucket:  Bucket name where the product will be stored.
        prefix:  Prefix in the bucket.
        s3_name: Output filename in the bucket.
    """
    try:
        access_key_id = os.environ['PUBLISH_ACCESS_KEY_ID']
        access_key_secret = os.environ['PUBLISH_SECRET_ACCESS_KEY']
    except KeyError:
        raise ValueError(
            'Please provide S3 Bucket upload access key credentials via the '
            'PUBLISH_ACCESS_KEY_ID and PUBLISH_SECRET_ACCESS_KEY environment variables'
        )

    s3_client = boto3.client('s3', aws_access_key_id=access_key_id, aws_secret_access_key=access_key_secret)

    if s3_name is None:
        s3_name = path_to_file.name
    key = str(Path(prefix) / s3_name)

    extra_args = {'ContentType': get_content_type(key)}

    s3_client.upload_file(str(path_to_file), bucket, key, extra_args)

    tag_set = get_tag_set(path_to_file.name)

    s3_client.put_object_tagging(Bucket=bucket, Key=key, Tagging=tag_set)


def process_gather_landsat(
    scene_name: str,
    aoi_db: str,
    points_db: str,
    bands: list,
    fireseason: int | None = None,
    publish_bucket: str | None = None,
    publish_bucket_prefix: str | None = None,
) -> None:
    """Download and clip Landsat image.

    Args:
        scene_name: Name of the LANDSAT scene.
        aoi_db:  Filename of the geojson with AOIs.
        points_db:  Filename of the geojson with fire points.
        fireseason:  Year for the fire season.
        bands: Bands to extract from scene.
        publish_bucket: AWS S3 bucket HyP3 for upload the final product(s).
        publish_bucket_prefix: Add a bucket prefix to product(s).
    """
    metadata, stac_gdf = find_landsat(scene_name)
    intersection = find_intersection(stac_gdf, Path(aoi_db), Path(points_db), fireseason)
    for band in bands:
        image = download_landsat(metadata, band)
        prefixes, filenames = clip_landsat(image, intersection)
        if publish_bucket is not None:
            for i in range(len(prefixes)):
                path = prefixes[i] / filenames[i]
                if publish_bucket_prefix is None:
                    upload_file_to_s3_with_publish_access_keys(path, publish_bucket, str(prefixes[i]))
                else:
                    upload_file_to_s3_with_publish_access_keys(path, publish_bucket, publish_bucket_prefix)


def geo_viirs_intersects(geo_path: Path, bbox: tuple[float, float, float, float]) -> bool:
    """Check if geographic file overlaps with bounding box.

    Args:
        geo_path: Path to geographic file.
        bbox: Tuple with lon/lat coordinates for bounding box (min_lon, min_lat, max_lon, max_lat).

    Returns:
        intersects: True if bounding box overlaps, False if it does not.
    """
    min_lon, min_lat, max_lon, max_lat = bbox

    geo = netCDF4.Dataset(geo_path)
    lon = geo.groups['geolocation_data']['longitude'][:]
    lat = geo.groups['geolocation_data']['latitude'][:]
    geo.close()

    cond_lon = np.logical_and(lon >= min_lon, lon <= max_lon)
    cond_lat = np.logical_and(lat >= min_lat, lat <= max_lat)
    cond = np.logical_and(cond_lon, cond_lat)

    if np.sum(cond) > 0:
        return True
    else:
        return False


def download_viirs_batch(results: list, batch: int, num: int, dest: str = './') -> None:
    """Download VIIRS batch.

    Args:
        results: List of results from earthaccess query.
        batch: Batch number.
        num: Batch size.
        dest: Destination folder.
    """
    threads = min(8, num)  # Don't try for more than 8 threads (the default).
    to_download = results[num * batch : num * batch + num]

    try:
        earthaccess.download(to_download, dest, threads=threads)
    except Exception as e:
        print('Downloading Error')
        print(e)
        print('Trying again with 1 thread')
        earthaccess.download(to_download, dest, threads=1)


def download_viirs(
    short_name: str, start_date: str, end_date: str, bbox: tuple[float, float, float, float] | None = None
) -> tuple[list, list]:
    """Download VIIRS images.

    Args:
        short_name: Short name for VIIRS data.
        start_date: Start date for the VIIRS data.
        end_date: End date for the VIIRS data.
        bbox: Tuple with bounding box lon/lat coordinates.

    Returns:
        geo: List of paths for geographic files.
        data: List of paths for data files.
    """
    short_name_list = list(short_name)
    if int(short_name[4]) == 2:
        short_name_list[4] = '3'
    elif int(short_name[4]) == 3:
        short_name_list[4] = '2'
    else:
        raise ValueError(f'The short name {short_name} does not have the correct format')
    if bbox is None:
        bbox = (-170.0, 54.0, -125.0, 72.0)
    short_name_add = ''.join(short_name_list)

    granules = earthaccess.search_data(short_name=short_name, bounding_box=bbox, temporal=(start_date, end_date))
    granules += earthaccess.search_data(short_name=short_name_add, bounding_box=bbox, temporal=(start_date, end_date))
    batchsize = 10
    batches = math.ceil(len(granules) / batchsize)
    num = min(len(granules), batchsize)  # number of images per batch
    for batch in range(batches):
        download_viirs_batch(granules, batch, num)

    dest = Path.cwd()
    data = sorted(dest.glob('VNP02*'))
    data += sorted(dest.glob('VJ102*'))
    data += sorted(dest.glob('VJ202*'))

    geo = sorted(dest.glob('VNP03*'))
    geo += sorted(dest.glob('VJ103*'))
    geo += sorted(dest.glob('VJ203*'))

    return geo, data


def clip_viirs(
    out_geo: list[Path], out_data: list[Path], bbox: tuple, fire_id: str, bands: list | None = None
) -> tuple[list, list]:
    """Download VIIRS images.

    Args:
        out_geo: Paths of downloaded geographic files.
        out_data: Paths of downloaded data files.
        bbox: Tuple with bounding box lon/lat coordinates.
        fire_id: Fire identifier.
        bands: Bands to extract from VIIRS.

    Returns:
        prefixes: List of prefixes for clipped files.
        filenames: List of filenames for clipped files.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    xs, ys, z1, z2 = utm.from_latlon(np.array([min_lat, max_lat]), np.array([min_lat, max_lat]))
    xs[0] = xs[0] - BUFFER
    xs[-1] = xs[-1] + BUFFER
    ys[0] = ys[0] - BUFFER
    ys[-1] = ys[-1] + BUFFER
    lats, lons = utm.to_latlon(xs, ys, z1, z2)
    min_lat = lats[0]
    max_lat = lats[-1]
    min_lon = lons[0]
    max_lon = lons[-1]
    widthi, heighti = int((xs[-1] - xs[0]) / 375 + 1), int((ys[-1] - ys[0]) / 375 + 1)
    widthm, heightm = int((xs[-1] - xs[0]) / 750 + 1), int((ys[-1] - ys[0]) / 750 + 1)

    prefixes, filenames = [], []
    for i in range(len(out_data)):
        dat = out_data[i]
        geo_path = out_geo[i]

        if 'MOD' in dat.name:
            width, height = widthm, heightm
            if bands is None:
                bands = [f'M{str(i + 1).zfill(2)}' for i in range(16)]
            elif np.sum(np.array(bands) > 16) > 0:
                raise ValueError('Some of the bands are > 16')
            else:
                bands = [f'M{str(band).zfill(2)}' for band in bands]
        else:
            width, height = widthi, heighti
            if bands is None:
                bands = [f'I{str(i + 1).zfill(2)}' for i in range(5)]
            elif np.sum(np.array(bands) > 5) > 0:
                raise ValueError('Some of the bands are > 5')
            else:
                bands = [f'I{str(band).zfill(2)}' for band in bands]

        geo = netCDF4.Dataset(geo_path.name)
        lon = geo.groups['geolocation_data']['longitude'][:]
        lat = geo.groups['geolocation_data']['latitude'][:]
        geo.close()

        data = netCDF4.Dataset(dat.name)
        band_data = [data.groups['observation_data'][band][:] for band in bands]
        data.close()

        swath = geometry.SwathDefinition(lons=lon, lats=lat)
        grid = geometry.AreaDefinition(
            'area', 'target grid', 'latlon', {'proj': 'latlong'}, width, height, [min_lon, min_lat, max_lon, max_lat]
        )

        for i, bd in enumerate(band_data):
            try:
                result = kd_tree.resample_nearest(swath, bd, grid, radius_of_influence=5000, fill_value=-9999)
            except Exception:
                print(f'Cannot process {bands[i]} on {geo.name}')
                continue
            transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)
            fire_year = dat.name[10:14]
            platform = dat.name[0:3]
            prefix = Path(f'{fire_year}/{fire_id}/{platform}/')
            filename = f'{fire_id}_{dat.name.replace(".nc", "")}_{bands[i]}.tif'
            filepath = prefix / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(
                filepath.resolve(),
                'w',
                driver='GTiff',
                height=height,
                width=width,
                count=1,
                dtype=result.dtype,
                crs='epsg:4326',
                transform=transform,
                nodata=0,
            ) as dst:
                dst.write(result, 1)
            prefixes.append(prefix)
            filenames.append(filename)
    return prefixes, filenames


def get_viirs_params_from_name(scene_name: str) -> tuple[str, datetime, datetime]:
    """Get parameters from VIIRS scene name.

    Args:
        scene_name: Name of the scene.

    Returns:
        short_name: Short name of the VIIRS file.
        start_date: Datetime one minute before the acquisition time.
        end_date: Datetime one minute after the acquisition time.
    """
    short_name = scene_name.split('.')[0]
    date = datetime.strptime(scene_name.split('.')[1] + '.' + scene_name.split('.')[2], 'A%Y%j.%H%M')
    start_date = date - timedelta(minutes=1)
    end_date = date + timedelta(minutes=1)

    return short_name, start_date, end_date


def process_gather_viirs(
    scene_name: str,
    aoi_db: str,
    points_db: str,
    bands: list | None = None,
    publish_bucket: str | None = None,
    publish_bucket_prefix: str | None = None,
) -> None:
    """Download and clip VIIRS image.

    Args:
        scene_name: Identifier of the VIIRS scene.
        aoi_db:  Filename of the geojson with AOIs.
        points_db:  Filename of the geojson with fire points.
        bands: Bands to extract from scene.
        publish_bucket: AWS S3 bucket HyP3 for upload the final product(s).
        publish_bucket_prefix: Add a bucket prefix to product(s).
    """
    if bands is not None:
        abands = [str(band) for band in bands]
        sbands = ''.join(abands)
        if 'I' in sbands and 'MOD' in scene_name:
            raise ValueError(f'{scene_name} does not have I bands')
        elif 'M' in sbands and 'IMG' in scene_name:
            raise ValueError(f'{scene_name} does not have M bands')
    short_name, start_image, end_image = get_viirs_params_from_name(scene_name)
    out_geo, out_data = download_viirs(
        short_name, start_image.strftime('%Y-%m-%dT%H:%M:%S'), end_image.strftime('%Y-%m-%dT%H:%M:%S')
    )
    gdf = join_dataframes(Path(aoi_db), Path(points_db), '4326')
    gdf = gdf[
        (gdf['start_date'] <= start_image.strftime('%Y-%m-%d')) & (gdf['end_date'] >= end_image.strftime('%Y-%m-%d'))
    ]
    geometries = list(gdf['geometry'])
    fire_ids = list(gdf['FIREID'])
    for i, geom in enumerate(geometries):
        bbox = geom.bounds
        fire_id = fire_ids[i]
        if geo_viirs_intersects(out_geo[0], bbox):
            prefixes, filenames = clip_viirs(out_geo, out_data, bbox, fire_id, bands)
            if publish_bucket is not None:
                for i in range(len(prefixes)):
                    path = prefixes[i] / filenames[i]
                    if publish_bucket_prefix is None:
                        upload_file_to_s3_with_publish_access_keys(path, publish_bucket, str(prefixes[i]))
                    else:
                        upload_file_to_s3_with_publish_access_keys(path, publish_bucket, publish_bucket_prefix)


def main() -> None:
    """HyP3 entrypoint for hyp3_akfire_safe."""
    parser = ArgumentParser()
    parser.add_argument('--publish-bucket', help='AWS S3 bucket HyP3 for upload the final product(s)')
    parser.add_argument('--publish-bucket-prefix', help='Add a bucket prefix to product(s)')
    parser.add_argument('--scene-name', type=str, help='Name of the scene')
    parser.add_argument('--aoi-db', type=str, help='File path for the AOI database')
    parser.add_argument('--points-db', type=str, help='File path for the fire points database')
    parser.add_argument('--fire-season', type=int, help='Year of the fire season')
    parser.add_argument(
        '--bands',
        type=str.split,
        nargs='+',
        help='Bands to extract',
    )

    args = parser.parse_args()

    args.bands = [int(item) for sublist in args.bands for item in sublist]

    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO
    )

    if 'LC' in args.scene_name:
        process_gather_landsat(
            scene_name=args.scene_name,
            aoi_db=args.aoi_db,
            points_db=args.points_db,
            bands=args.bands,
            fireseason=args.fire_season,
            publish_bucket=args.publish_bucket,
            publish_bucket_prefix=args.publish_bucket_prefix,
        )
    elif 'V' == args.scene_name[0]:
        process_gather_viirs(
            scene_name=args.scene_name,
            aoi_db=args.aoi_db,
            points_db=args.points_db,
            bands=args.bands,
            publish_bucket=args.publish_bucket,
            publish_bucket_prefix=args.publish_bucket_prefix,
        )
