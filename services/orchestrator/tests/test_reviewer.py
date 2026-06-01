from die_firma.reviewer import review


def test_no_command_passes(tmp_path):
    assert review(None, tmp_path).passed
    assert review("   ", tmp_path).passed


def test_command_exit_code_decides(tmp_path):
    assert review("true", tmp_path).passed
    failed = review("echo oops; false", tmp_path)
    assert not failed.passed
    assert "oops" in failed.detail
