"""feds processing."""

import datetime as dt
import os
import shutil
from argparse import ArgumentParser
from pathlib import Path

import boto3
import botocore
from fireatlas import FireMain, FireTime, postprocess, preprocess, settings
from hyp3lib.aws import upload_file_to_s3
from hyp3lib.util import string_is_true
from tqdm.auto import tqdm

import hyp3_akfire_safe as has
from hyp3_akfire_safe.aurora import upload_gdf_to_db


settings.READ_LOCATION = 'local'
settings.remove_static_sources = True
settings.LOCAL_PATH = '.'


def download_data(input_bucket: str, input_prefix: str) -> None:
    """Download files from s3 bucket and make folder structure.

    Args:
        input_bucket: Bucket with fire detection text files.
        input_prefix: Prefix with fire detection text files.
    """
    s3 = boto3.resource('s3', config=boto3.session.Config(signature_version=botocore.UNSIGNED))
    buck = s3.Bucket(input_bucket)
    for s3_object in tqdm(buck.objects.filter(Prefix=f'{input_prefix}')):
        path, filename = os.path.split(s3_object.key)
        if '.txt' in filename:
            date = dt.datetime.strptime(filename.split('_')[2], 'd%Y%m%d')
            folder = Path(date.strftime('data/%Y/%m/%d'))
            folder.mkdir(parents=True, exist_ok=True)
            buck.download_file(s3_object.key, f'{str(folder)}/{filename}')


def rewrite_files(
    root: str | None, input_bucket: str | None = None, input_prefix: str | None = None
) -> tuple[dt.datetime, dt.datetime]:
    """Rewrites the files so they have the same format of SNPP or NOAA20.

    Args:
        root: Path to the directory that has all the text files.
        input_bucket: Bucket with fire detection text files.
        input_prefix: Prefix with fire detection text files.

    Returns:
        start_date: First available date in the folder.
        end_date: Last available date in the folder.
    """
    if root is None:
        download_data(str(input_bucket), str(input_prefix))
        root = 'data'

    output_path = Path('./FEDSinput/VIIRS/VJ114IMGTDL')
    output_path.mkdir(parents=True, exist_ok=True)
    output = str(output_path)
    dates = []
    for path, subdirs, files in os.walk(root):
        sfiles = [path + '/' + f for f in files]
        for sf in sfiles:
            fecha = dt.datetime.strptime(Path(sf).name.split('_')[2] + Path(sf).name.split('_')[3][0:5], 'd%Y%m%dt%H%M')
            dates.append(fecha)
            with Path(sf).open() as f:
                lines = [line.replace(' ', '') for line in f.readlines() if '#' not in line]
            outname = fecha.strftime('J1_VIIRS_C2_Global_VJ114IMGTDL_NRT_%Y%j.txt')
            if not Path(output + '/' + outname).exists():
                header = 'latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n'
                outlines = [header]
            else:
                with Path(output + '/' + outname).open() as f:
                    outlines = [line for line in f.readlines()]
            for line in lines:
                if line.split(',')[5] == '8':
                    conf = 'nominal'
                elif line.split(',')[5] == '9':
                    conf = 'high'
                else:
                    conf = 'low'
                newline = (
                    ','.join(line.split(',')[0:5])
                    + fecha.strftime(',%Y-%m-%d')
                    + fecha.strftime(',%H:%M')
                    + ',N,'
                    + conf
                    + ',2.0NRT,'
                    + line.split(',')[2]
                    + ','
                    + line.split(',')[6]
                    + ',N\n'
                )
                outlines.append(newline)
            with Path(output + '/' + outname).open('w') as f:
                for line in outlines:
                    f.write(line)
    dates = sorted(dates)

    return dates[0], dates[-1]


def copy_aux() -> None:
    """Copy auxiliary files to work directory."""
    source = Path(has.__file__).parent / 'aux' / 'VIIRS_Global_flaring_d.7_slope_0.029353_2017_web_v1.csv'
    dest = Path('./FEDSinput/static_sources/VIIRS_Global_flaring_d.7_slope_0.029353_2017_web_v1.csv')
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)

    source = Path(has.__file__).parent / 'aux' / 'nlcd_export_510m_simplified_latlon.tif'
    dest = Path('./FEDSpreprocessed/nlcd_export_510m_simplified_latlon.tif')
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)


def get_name(extent: list, start: str, end: str) -> str:
    """Get name for output json.

    Args:
        extent: List of coordinates for query.
        start:  The start date of the images
        end:  The end date of the images

    Returns:
        Filename of the json file
    """
    name = 'FEDS_PERIMETER'
    fextent = [float(ext) for ext in extent]
    lons = ['E' + str(round(abs(lon))) if lon >= 0 else 'W' + str(round(abs(lon))) for lon in [fextent[0], fextent[2]]]
    lats = ['N' + str(round(abs(lat))) if lat >= 0 else 'S' + str(round(abs(lat))) for lat in [fextent[1], fextent[3]]]

    strextent = '_'.join(lons + lats)

    nstart = start.replace('-', '')
    nend = end.replace('-', '')

    name = f'{name}_{strextent}_{nstart}_{nend}.parquet'

    return name


def nullable_string(argument_string: str) -> str | None:
    """Identify if string is None.

    Takes:
    argument_string: Input string.

    Returns: None if input string is 'None' else input string
    """
    argument_string = argument_string.replace('None', '').strip()
    return argument_string if argument_string else None


def feds(
    extent: list,
    path: str | None = None,
    start: str | None = None,
    end: str | None = None,
    input_bucket: str | None = None,
    input_prefix: str | None = None,
    bucket: str | None = None,
    bucket_prefix: str = '',
    upload_to_db: bool = False,
) -> None:
    """This runs the FEDS algorithm.

    Args:
        path: List with lon/lat coordinates.
        extent: List with lon/lat coordinates.
        start:  The start date of the images
        end:  The end date of the images
        input_bucket: Bucket with fire detection text files.
        input_prefix: Prefix with fire detection text files.
        bucket: AWS S3 bucket HyP3 for upload the final product(s)
        bucket_prefix: Add a bucket prefix to product(s)
        upload_to_db: Whether or not to upload the data to an AWS Aurora database.
    """
    # This preprocess the files from GINA
    if path is None and input_bucket is None:
        raise ValueError('Local path and input bucket are not provided')
    elif path is None and input_prefix is None:
        raise ValueError('Local path and input prefix are not provided')

    startt, endt = rewrite_files(path, input_bucket, input_prefix)
    copy_aux()

    # 01_Ingest
    region = ('AOI', [float(coord) for coord in extent])

    preprocess.preprocess_region(region, force=True)

    if start is None:
        start_date = startt
        start = startt.strftime('%Y-%m-%dT%H:%M')
    else:
        start_date = dt.datetime.strptime(start, '%Y-%m-%dT%H:%M')

    if end is None:
        end_date = endt
        end = endt.strftime('%Y-%m-%dT%H:%M')
    else:
        end_date = dt.datetime.strptime(end, '%Y-%m-%dT%H:%M')

    tst = [
        int(start_date.strftime('%Y')),
        int(start_date.strftime('%m')),
        int(start_date.strftime('%d')),
        start_date.strftime('%p'),
    ]
    ted = [
        int(end_date.strftime('%Y')),
        int(end_date.strftime('%m')),
        int(end_date.strftime('%d')),
        end_date.strftime('%p'),
    ]
    list_of_ts = list(FireTime.t_generator(tst, ted))

    sat = 'NOAA20'
    for t in list_of_ts[::2]:
        preprocess.preprocess_NRT_file(t, sat)

    for t in list_of_ts:
        preprocess.preprocess_region_t(t, region=region, read_location='local', force=True)

    # 02_Run
    region_run = ['AOI']
    allfires, allpixels, t_saved = FireMain.Fire_Forward(
        tst=tst, ted=ted, restart=False, region=region_run, read_location='local'
    )

    # 03_Output
    allfires_gdf = postprocess.read_allfires_gdf(tst, ted, region_run, location='local').reset_index()

    output_name = get_name(extent, start, end)
    allfires_gdf.to_parquet(output_name)

    if upload_to_db:
        upload_gdf_to_db(allfires_gdf)

    if bucket:
        upload_file_to_s3(Path(output_name), bucket, bucket_prefix)


def main() -> None:
    """HyP3 entrypoint for pull_perimeter."""
    parser = ArgumentParser()
    parser.add_argument('--bucket', help='AWS S3 bucket HyP3 for upload the final product(s)')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to product(s)')
    parser.add_argument(
        '--upload-to-db', type=string_is_true, default=False, help='Add the data to the AWS Aurora database.'
    )
    parser.add_argument(
        '--start-date', type=nullable_string, default=None, help='Start date of the images (YYYY-MM-DDTHH:MM)'
    )
    parser.add_argument(
        '--end-date', type=nullable_string, default=None, help='End date of the images (YYYY-MM-DDTHH:MM)'
    )
    parser.add_argument('--extent', type=str.split, nargs='+', help='min_lon min_lat max_lon max_lat')
    parser.add_argument('--path', type=nullable_string, default=None, help='Folder path with fire pixels')
    parser.add_argument('--input-bucket', type=nullable_string, default=None, help='Bucket with fire detections')
    parser.add_argument('--input-prefix', type=nullable_string, default=None, help='Prefix with fire detections')

    args = parser.parse_args()

    args.extent = [item for sublist in args.extent for item in sublist]

    feds(
        extent=args.extent,
        path=args.path,
        start=args.start_date,
        end=args.end_date,
        bucket=args.bucket,
        bucket_prefix=args.bucket_prefix,
        input_bucket=args.input_bucket,
        input_prefix=args.input_prefix,
        upload_to_db=args.upload_to_db,
    )
