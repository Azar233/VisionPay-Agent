import pytest

from app.api.camera import normalize_ip_webcam_url


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        ("http://192.168.1.20:8080", "http://192.168.1.20:8080/video"),
        ("http://10.0.0.8/video", "http://10.0.0.8:8080/video"),
        ("http://172.16.2.3:9000/videofeed", "http://172.16.2.3:9000/videofeed"),
    ],
)
def test_normalize_ip_webcam_url(raw_url, expected):
    assert normalize_ip_webcam_url(raw_url) == expected


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://192.168.1.20:8080",
        "http://example.com:8080",
        "http://127.0.0.1:8080/video",
        "http://127.0.0.1:8080/admin",
        "http://user:password@192.168.1.20:8080",
    ],
)
def test_normalize_ip_webcam_url_rejects_unsafe_addresses(raw_url):
    with pytest.raises(ValueError):
        normalize_ip_webcam_url(raw_url)


def test_ip_webcam_proxy_rejects_invalid_url(client):
    response = client.get("/api/camera/ip-webcam/stream", params={"url": "https://192.168.1.20"})
    assert response.status_code == 400
    assert response.json()["message"] == "IP Webcam 地址必须以 http:// 开头"
