"""Chart SSR 客户端单测（mock HTTP + 本地降级）。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.chart.ssr_client import render_chart_to_path_sync
from config.settings import Settings


def _settings(**overrides) -> Settings:
    base = {
        "jwt_secret": "test-secret-min-32-chars-long-enough",
        "chart_ssr_enabled": False,
        "chart_ssr_url": "http://127.0.0.1:3001",
        "chart_ssr_timeout_ms": 1000,
        "chart_ssr_width": 400,
        "chart_ssr_height": 240,
    }
    base.update(overrides)
    return Settings(**base)


def test_render_local_fallback(tmp_path: Path):
    out = tmp_path / "chart.png"
    path = render_chart_to_path_sync(
        chart_spec={"chartType": "bar", "xColumn": "A", "yColumns": ["B"], "status": "ready"},
        columns=["A", "B"],
        rows=[["x", 1], ["y", 2]],
        output_path=out,
        settings=_settings(),
    )
    assert path is not None
    assert out.is_file()


def test_render_ssr_png_base64(tmp_path: Path):
    out = tmp_path / "ssr.png"
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"pngBase64": "iVBORw0KGgo="}  # invalid but decode tested separately

    with patch("app.chart.ssr_client.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        client_cls.return_value = client

        # invalid base64 will fail decode - use real minimal png b64
        import base64

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        mock_resp.json.return_value = {"pngBase64": base64.b64encode(png_bytes).decode()}

        path = render_chart_to_path_sync(
            chart_spec={"chartType": "bar", "status": "ready"},
            columns=["A", "B"],
            rows=[["x", 1]],
            output_path=out,
            settings=_settings(chart_ssr_enabled=True),
        )
        assert path is not None
        assert out.is_file()
