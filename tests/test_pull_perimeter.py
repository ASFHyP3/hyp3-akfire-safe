from datetime import datetime
from pathlib import Path

from hyp3_akfire_safe import pull_perimeter as pp


def test_get_product_name():
    extent = [-1.2, -0.1, 4.7, 5.8]
    start = '0000-00-00'
    end = '1111-11-11'
    assert pp.get_name(extent, start, end) == 'FIRE_PERIMETER_W1_E5_S0_N6_00000000_11111111.parquet'


def test_pull_perimeter():
    extent = '-169.01 52.37 -130.16 71.66'.split()
    start = '2025-06-01'
    end = datetime.now().strftime('%Y-%m-%d')

    pp.pull_perimeter(extent, start, end)

    assert Path(f'FIRE_PERIMETER_W169_W130_N52_N72_{start.replace("-", "")}_{end.replace("-", "")}.parquet').exists()

    Path(f'FIRE_PERIMETER_W169_W130_N52_N72_{start.replace("-", "")}_{end.replace("-", "")}.parquet').unlink()
