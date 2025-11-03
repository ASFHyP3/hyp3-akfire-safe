def test_hyp3_akfire_safe(script_runner):
    ret = script_runner.run(['python', '-m', 'hyp3_akfire_safe', '-h'])
    assert ret.success
