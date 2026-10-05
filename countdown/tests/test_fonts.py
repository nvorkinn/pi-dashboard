import io

from countdown_core.utils import utils


def test_google_symbols_downloads_once_on_first_use_and_then_reads_the_cached_file(tmp_path, monkeypatch):
    stand_in = (utils.FONTS_DIR / "Ubuntu-Regular.ttf").read_bytes()
    monkeypatch.setattr(utils, "FONTS_DIR", tmp_path / "fonts")
    urls = []

    def fake_urlopen(url, timeout):
        urls.append(url)
        return io.BytesIO(stand_in)

    monkeypatch.setattr(utils.urllib.request, "urlopen", fake_urlopen)
    utils.google_symbols.cache_clear()
    try:
        utils.google_symbols()
        assert len(urls) == 1
        assert [p.name for p in (tmp_path / "fonts").iterdir()] == ["MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].ttf"]

        utils.google_symbols.cache_clear()  # as if the app restarted: the file on disk is reused
        utils.google_symbols()
        assert len(urls) == 1
    finally:
        utils.google_symbols.cache_clear()  # don't leave the stand-in cached for other tests
