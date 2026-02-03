"""gather-landsat processing."""

import logging
import os
from argparse import ArgumentParser
from pathlib import Path

import boto3
import geopandas as gpd
import pandas as pd
import pystac_client
from hyp3lib.aws import get_content_type, get_tag_set
from osgeo import gdal


gdal.UseExceptions()

LANDSAT_CATALOG_API = 'https://landsatlook.usgs.gov/stac-server'
LANDSAT_CATALOG = pystac_client.Client.open(LANDSAT_CATALOG_API)
LANDSAT_BUCKET = 'usgs-landsat'


log = logging.getLogger(__name__)


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


def find_intersection(stac: gpd.GeoDataFrame, aoi: Path, fireseason: int | None) -> gpd.GeoDataFrame:
    """Find intersection between image and AOIs.

    Args:
        stac: DataFrame with image metadata.
        aoi: Path of database with AOIs.
        fireseason: Year of the fire season.

    Returns:
        intersection: Dataframe with Polygons of the intersections.
    """
    gdf_aoi = gpd.read_file(str(aoi))
    if fireseason is not None:
        gdf_aoi = gdf_aoi[gdf_aoi['FIREYEAR'] == str(fireseason)]
    gdf_aoi = gdf_aoi.to_crs(str(stac.crs))
    gdf_aoi['start_date'] = (
        pd.to_datetime(gdf_aoi['PERIMETERDATE'], unit='ms').dt.tz_localize('America/Anchorage').dt.tz_convert('UTC')
    )
    gdf_aoi['end_date'] = (
        pd.to_datetime(gdf_aoi['FPOUTDATE'], unit='ms').dt.tz_localize('America/Anchorage').dt.tz_convert('UTC')
    )
    inter = gpd.overlay(stac, gdf_aoi, how='intersection').to_crs(f'{stac["proj:code"][0]}')
    inter = inter[(inter['start_date'] <= inter['datetime']) & (inter['end_date'] >= inter['datetime'])]
    if inter.empty:
        raise RuntimeError(f'The scene {stac["id"][0]} does not overlap with any fires in {fireseason}')
    return inter


def clip_image(scene: Path, inter: gpd.GeoDataFrame) -> tuple[list[Path], list[str]]:
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
        bbox = [geom.bounds[0], geom.bounds[3], geom.bounds[2], geom.bounds[1]]
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


def find_scene(scene_name: str) -> tuple[dict, gpd.GeoDataFrame]:
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


def download_scene(metadata: dict, band: int) -> Path:
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
    bands: list,
    fireseason: int | None = None,
    publish_bucket: str | None = None,
    publish_bucket_prefix: str | None = None,
) -> None:
    """Download and clip Landsat image.

    Args:
        scene_name: Name of the LANDSAT scene.
        aoi_db:  Filename of the geojson with AOIs.
        fireseason:  Year for the fire season.
        bands: Bands to extract from scene.
        bucket: AWS S3 bucket HyP3 for upload the final product(s).
        bucket_prefix: Add a bucket prefix to product(s).
    """
    metadata, stac_gdf = find_scene(scene_name)
    intersection = find_intersection(stac_gdf, Path(aoi_db), fireseason)
    for band in bands:
        image = download_scene(metadata, band)
        prefixes, filenames = clip_image(image, intersection)
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

    process_gather_landsat(
        scene_name=args.scene_name,
        aoi_db=args.aoi_db,
        bands=args.bands,
        fireseason=args.fire_season,
        publish_bucket=args.publish_bucket,
        publish_bucket_prefix=args.publish_bucket_prefix,
    )
