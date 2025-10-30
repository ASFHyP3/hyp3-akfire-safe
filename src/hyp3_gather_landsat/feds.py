"""pull-perimeter processing."""

import datetime as dt
import math
import os
import shutil
from argparse import ArgumentParser
from pathlib import Path

import geopandas as gpd
import hyp3_gather_landsat as hgl
from fireatlas import FireMain, FireTime, FireObj, preprocess, postprocess, settings
from hyp3lib.aws import upload_file_to_s3
from owslib.ogcapi.features import Features


settings.READ_LOCATION='local'
settings.remove_static_sources=True
settings.LOCAL_PATH='.'


def rewrite_files(root: str) -> None:
    output = Path('./FEDSinput/VIIRS/VJ114IMGTDL')
    output.mkdir(parents=True, exist_ok=True)
    output = str(output)
    for path, subdirs, files in os.walk(root):
        sfiles = [path+'/'+f for f in files]
        for sf in sfiles:
            fecha = dt.datetime.strptime(os.path.basename(sf).split('_')[2]+os.path.basename(sf).split('_')[3][0:5],'d%Y%m%dt%H%M')
            f = open(sf,'r')
            lines = [line.replace(' ','') for line in f.readlines() if '#' not in line]
            f.close()
            outname = fecha.strftime('J1_VIIRS_C2_Global_VJ114IMGTDL_NRT_%Y%j.txt')
            if not os.path.exists(output+'/'+outname):
                header = 'latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n'
                outlines = [header]
                f = open(output+'/'+outname,'w')
            else:
                f = open(output+'/'+outname,'r')
                outlines = [line for line in f.readlines()]
                f.close()
                f = open(output+'/'+outname,'w')
            for line in lines:
                if line.split(',')[5]=='8':
                    conf = 'nominal'
                elif line.split(',')[5]=='9':
                    conf = 'high'
                else:
                    conf = 'low'
                newline = ','.join(line.split(',')[0:5])+fecha.strftime(',%Y-%m-%d')+fecha.strftime(',%H:%M')+',N,'+conf+',2.0NRT,'+line.split(',')[2]+','+line.split(',')[6]+',N\n'
                outlines.append(newline)
            for line in outlines:
                f.write(line)
            f.close()


def copy_aux() -> None:
    source = Path(hgl.__file__).parent / 'aux' / 'VIIRS_Global_flaring_d.7_slope_0.029353_2017_web_v1.csv'
    dest = Path('./FEDSinput/static_sources/VIIRS_Global_flaring_d.7_slope_0.029353_2017_web_v1.csv')
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)

    source = Path(hgl.__file__).parent / 'aux' / 'nlcd_export_510m_simplified_latlon.tif'
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


def feds(
    path: list,
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
    #This preprocess the files from GINA
    rewrite_files(path)
    copy_aux()

    #01_Ingest
    region = ('AOI',[float(coord) for coord in extent])

    preprocess.preprocess_region(region, force=True)

    start_date = dt.datetime.strptime(start, '%Y-%m-%dT%H:%M')
    end_date = dt.datetime.strptime(end, '%Y-%m-%dT%H:%M')

    tst = [int(start_date.strftime('%Y')), int(start_date.strftime('%m')), int(start_date.strftime('%d')), start_date.strftime('%p')]
    ted = [int(end_date.strftime('%Y')), int(end_date.strftime('%m')), int(end_date.strftime('%d')), end_date.strftime('%p')]
    list_of_ts = list(FireTime.t_generator(tst, ted))

    sat = "NOAA20"
    for t in list_of_ts[::2]:
        preprocess.preprocess_NRT_file(t, sat)

    for t in list_of_ts:
        preprocess.preprocess_region_t(t, region=region, read_location="local", force=True)

    #02_Run
    region = ['AOI']
    allfires, allpixels, t_saved = FireMain.Fire_Forward(tst=tst, ted=ted, restart=False, region=region, read_location="local")

    #03_Output
    allfires_gdf = postprocess.read_allfires_gdf(tst, ted, region, location="local")

    output_name = get_name(extent, start, end)
    allfires_gdf.to_parquet(output_name)

    if bucket:
        upload_file_to_s3(Path(output_name), bucket, bucket_prefix)


def main() -> None:
    """HyP3 entrypoint for pull_perimeter."""
    parser = ArgumentParser()
    parser.add_argument('--bucket', help='AWS S3 bucket HyP3 for upload the final product(s)')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to product(s)')
    parser.add_argument('--start-date', type=str, help='Start date of the images (YYYY-MM-DDTHH:MM)')
    parser.add_argument('--end-date', type=str, help='End date of the images (YYYY-MM-DDTHH:MM)')
    # TODO: Your arguments here
    parser.add_argument(
        '--extent',
        type=str.split,
        nargs='+',
        help='min_lon min_lat max_lon max_lat',
    )
    parser.add_argument('--path', type=str, help='Folder path with fire pixels')

    args = parser.parse_args()

    args.extent = [item for sublist in args.extent for item in sublist]

    feds(
        path=args.path,
        extent=args.extent,
        start=args.start_date,
        end=args.end_date,
        bucket=args.bucket,
        bucket_prefix=args.bucket_prefix,
    )
