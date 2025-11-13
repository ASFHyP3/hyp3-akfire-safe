from hyp3_akfire_safe import gather_landsat as process


def test_get_lc2_path():
    metadata = {'id': 'L--5', 'assets': {'B2.TIF': {'href': 'foo'}}}
    assert process.get_lc2_path(metadata) == 'foo'

    metadata = {'id': 'L--5', 'assets': {'green': {'href': 'foo'}}}
    assert process.get_lc2_path(metadata) == 'foo'

    metadata = {'id': 'L--8', 'assets': {'B8.TIF': {'href': 'foo'}}}
    assert process.get_lc2_path(metadata) == 'foo'

    metadata = {'id': 'L--8', 'assets': {'pan': {'href': 'foo'}}}
    assert process.get_lc2_path(metadata) == 'foo'


def test_get_product_name():
    assert process.get_product_name('1', '2') == 'LANDSAT_1_2'

    assert process.get_product_name('1990-01-01', '1991-01-01') == 'LANDSAT_19900101_19910101'
