"""gather-landsat processing."""

import logging
import os
import warnings
from argparse import ArgumentParser
from pathlib import Path
from shutil import make_archive

import pystac_client
from hyp3lib.aws import upload_file_to_s3
from osgeo import gdal


gdal.UseExceptions()

LANDSAT_CATALOG_API = 'https://landsatlook.usgs.gov/stac-server'
LANDSAT_CATALOG = pystac_client.Client.open(LANDSAT_CATALOG_API)
LANDSAT_BUCKET = 'usgs-landsat'


log = logging.getLogger(__name__)


def get_lc2_path(metadata: dict) -> str:
    """Get Landsat link.

    Args:
        metadata: Dictionary from json file associated with the Landsat image.

    Returns:
        Bucket link for Landsat image.
    """
    if metadata['id'][3] in ('4', '5'):
        band = metadata['assets'].get('B2.TIF')
        if band is None:
            band = metadata['assets']['green']
    elif metadata['id'][3] in ('7', '8', '9'):
        band = metadata['assets'].get('B8.TIF')
        if band is None:
            band = metadata['assets']['pan']
    else:
        raise NotImplementedError(f'AK Fire Safe processing not available for this platform. {metadata["id"][:3]}')

    return band['href'].replace('https://landsatlook.usgs.gov/data/', f'/vsis3/{LANDSAT_BUCKET}/')


def get_product_name(start_date: str, end_date: str) -> str:
    """Get the name of the compressed file.

    Args:
        start_date:  The start date of the images
        end_date:  The end date of the images

    Returns:
        Filename of the compressed file
    """
    start = start_date.replace('-', '')
    end = end_date.replace('-', '')

    return f'LANDSAT_{start}_{end}'


def process_gather_landsat(
    location: list,
    start_date: str,
    end_date: str,
    bucket: str | None = None,
    bucket_prefix: str = '',
) -> None:
    """Download a Landsat image.

    Args:
        location: List with lon/lat coordinates.
        start_date:  The start date of the images
        end_date:  The end date of the images
        bucket: AWS S3 bucket HyP3 for upload the final product(s)
        bucket_prefix: Add a bucket prefix to product(s)
    """
    os.environ['AWS_REGION'] = 'us-west-2'
    os.environ['AWS_REQUEST_PAYER'] = 'requester'
    gdal.SetConfigOption('AWS_REGION', 'us-west-2')
    gdal.SetConfigOption('AWS_REQUEST_PAYER', 'requester')

    lon = location[0]
    lat = location[1]
    search = LANDSAT_CATALOG.search(
        collections=['landsat-c2l1'],  # Landsat 8 collection
        datetime=f'{start_date}/{end_date}',
        intersects={'type': 'Point', 'coordinates': [float(lon), float(lat)]},  # Coordinates
    )

    product_name = get_product_name(start_date, end_date)
    product_dir = Path(product_name)
    product_dir.mkdir(parents=True, exist_ok=True)

    for item in list(search.items()):
        url = get_lc2_path(item.to_dict())
        filename = url.split('/')[-1]
        product_path = f'{product_name}/{filename}'
        try:
            gdal.Translate(product_path, url)
        except RuntimeError as e:
            if 'The specified key does not exist.' in str(e):
                warnings.warn(f'The S3 bucket does not have the file {filename}', UserWarning)
            else:
                raise e

    output_zip = make_archive(base_name=product_name, format='zip', base_dir=product_name)

    if bucket:
        upload_file_to_s3(Path(output_zip), bucket, bucket_prefix)


def main() -> None:
    """HyP3 entrypoint for hyp3_akfire_safe."""
    parser = ArgumentParser()
    parser.add_argument('--bucket', help='AWS S3 bucket HyP3 for upload the final product(s)')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to product(s)')
    parser.add_argument('--start-date', type=str, help='Start date of the images (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date of the images (YYYY-MM-DD)')
    # TODO: Your arguments here
    parser.add_argument(
        '--location',
        type=str.split,
        nargs='+',
        help='LON LAT',
    )

    args = parser.parse_args()

    args.location = [item for sublist in args.location for item in sublist]

    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO
    )

    process_gather_landsat(
        location=args.location,
        start_date=args.start_date,
        end_date=args.end_date,
        bucket=args.bucket,
        bucket_prefix=args.bucket_prefix,
    )
