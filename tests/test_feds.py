import shutil
from pathlib import Path

from hyp3_akfire_safe import feds


def test_get_product_name():
    extent = [-1.2, -0.1, 4.7, 5.8]
    start = '0000-00-00T00:00'
    end = '1111-11-11T11:11'
    assert feds.get_name(extent, start, end) == 'FEDS_PERIMETER_W1_E5_S0_N6_00000000T00:00_11111111T11:11.parquet'


def test_rewrite_files():
    root = Path('root/sub/year/month/day')
    root.mkdir(parents=True, exist_ok=True)
    txt = root / 'AFIMG_npp_d20250101_t0000000_e1111111_b00000_c20250101000000000000_cspp_dev.txt'
    with txt.open('w') as r:
        r.write('61.38845062, -137.02651978,  348.02493286,  0.375,  0.375,    8,   56.84369278,    0\n')
        r.write('61.43948364, -137.08790588,  339.97628784,  0.375,  0.375,    8,    3.56440330,    0\n')

    feds.rewrite_files('root')

    output = Path('FEDSinput/VIIRS/VJ114IMGTDL/J1_VIIRS_C2_Global_VJ114IMGTDL_NRT_2025001.txt')

    assert output.exists()
    with output.open() as out:
        lines = out.readlines()
        assert len(lines) == 3

    shutil.rmtree(Path('root'))
    shutil.rmtree(Path('FEDSinput'))


def test_feds():
    root = Path('root/sub/year/month/day')
    root.mkdir(parents=True, exist_ok=True)
    txt = root / 'AFIMG_npp_d20250101_t1111111_e1111111_b00000_c20250101000000000000_cspp_dev.txt'

    with txt.open('w') as r:
        r.write('61.38845062, -137.02651978,  348.02493286,  0.375,  0.375,    8,   56.84369278,    0\n')
        r.write('61.43948364, -137.08790588,  339.97628784,  0.375,  0.375,    8,    3.56440330,    0\n')

    path = 'root'
    start = '2025-01-01T00:00'
    end = '2025-01-01T23:00'
    extent = '-169.01 52.37 -130.16 71.66'.split()
    feds.feds(path, extent, start, end)

    output = Path('FEDS_PERIMETER_W169_W130_N52_N72_20250101T00:00_20250101T23:00.parquet')
    assert output.exists()

    output.unlink()
    shutil.rmtree(Path('root'))
    shutil.rmtree(Path('FEDSinput'))
    shutil.rmtree(Path('FEDSpreprocessed'))
    shutil.rmtree(Path('FEDSoutput-v3'))
