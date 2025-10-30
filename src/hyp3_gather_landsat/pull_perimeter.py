"""pull-perimeter processing."""

import datetime as dt
import math
from argparse import ArgumentParser
from pathlib import Path

import geopandas as gpd
from hyp3lib.aws import upload_file_to_s3
from owslib.ogcapi.features import Features


def iter_features_offset(
    w: Features,
    collection_id: str,
    params: dict | None = None,
    page_size: int = 100,
    max_pages: int | None = None,
    progress: bool = True,
) -> list:
    """Paginate through OGC API Features using offset parameter.

    Args:
        w: Feature collections.
        collection_id: Collection ID.
        params: Parameters to filter the search.
        page_size: Number of pages for the result.
        max_pages: Maximum number of pages.
        progress: Display search progress.

    Returns:
        List of features.
    """
    params = dict(params or {})

    # Get total count with minimal data
    meta_params = dict(params)
    meta_params['limit'] = 1
    meta = w.collection_items(collection_id, **meta_params)
    total = meta.get('numberMatched', 0)

    if total == 0:
        if progress:
            print('No matching features')
        return []
    # Round up the division here for total number of pages
    pages = math.ceil(total / page_size)

    # Support a user-defined page limit
    if max_pages and max_pages < pages:
        pages = max_pages

    all_features = []

    for i in range(pages):
        offset = i * page_size
        page_params = dict(params)
        page_params['limit'] = page_size
        page_params['offset'] = offset

        page = w.collection_items(collection_id, **page_params)
        features = page.get('features', [])
        all_features.extend(features)

        if progress:
            print(f'Page {i + 1}/{pages}: {len(all_features)}/{total} features')

        if len(features) < page_size:
            break

    return all_features


def get_name(extent: list, start: str, end: str) -> str:
    """Get name for output json.

    Args:
        extent: List of coordinates for query.
        start:  The start date of the images
        end:  The end date of the images

    Returns:
        Filename of the json file
    """
    name = 'FIRE_PERIMETER'
    fextent = [float(ext) for ext in extent]
    lons = ['E' + str(round(abs(lon))) if lon >= 0 else 'W' + str(round(abs(lon))) for lon in [fextent[0], fextent[2]]]
    lats = ['N' + str(round(abs(lat))) if lat >= 0 else 'S' + str(round(abs(lat))) for lat in [fextent[1], fextent[3]]]

    strextent = '_'.join(lons + lats)

    nstart = start.replace('-', '')
    nend = end.replace('-', '')

    name = f'{name}_{strextent}_{nstart}_{nend}.parquet'

    return name


def pull_perimeter(
    extent: list,
    start: str,
    end: str,
    bucket: str | None = None,
    bucket_prefix: str = '',
) -> None:
    """Pull perimeter.

    Args:
        extent: List with lon/lat coordinates.
        start:  The start date of the images
        end:  The end date of the images
        bucket: AWS S3 bucket HyP3 for upload the final product(s)
        bucket_prefix: Add a bucket prefix to product(s)
    """
    output_name = get_name(extent, start, end)
    OGC_URL = 'https://openveda.cloud/api/features'

    api = Features(url=OGC_URL)
    api.feature_collections()

    start_date = dt.datetime.strptime(start, '%Y-%m-%d')
    start = dt.datetime.strftime(start_date, '%Y-%m-%dT%H:%M:%S+00:00')
    end_date = dt.datetime.strptime(end, '%Y-%m-%d')
    end = dt.datetime.strftime(end_date, '%Y-%m-%dT%H:%M:%S+00:00')

    params = {'bbox': extent, 'datetime': [start + '/' + end], 'filter': 'farea>4'}

    features = iter_features_offset(
        api,
        collection_id='public.eis_fire_lf_perimeter_nrt',
        params=params,
        page_size=1000,
        progress=True,
    )

    lf = gpd.GeoDataFrame.from_features(features).set_crs('EPSG:4326')

    lf.to_parquet(output_name)

    if bucket:
        upload_file_to_s3(Path(output_name), bucket, bucket_prefix)


def main() -> None:
    """HyP3 entrypoint for pull_perimeter."""
    parser = ArgumentParser()
    parser.add_argument('--bucket', help='AWS S3 bucket HyP3 for upload the final product(s)')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to product(s)')
    parser.add_argument('--start-date', type=str, help='Start date of the images (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date of the images (YYYY-MM-DD)')
    # TODO: Your arguments here
    parser.add_argument(
        '--extent',
        type=str.split,
        nargs='+',
        help='min_lon min_lat max_lon max_lat',
    )

    args = parser.parse_args()

    args.extent = [item for sublist in args.extent for item in sublist]

    pull_perimeter(
        extent=args.extent,
        start=args.start_date,
        end=args.end_date,
        bucket=args.bucket,
        bucket_prefix=args.bucket_prefix,
    )
