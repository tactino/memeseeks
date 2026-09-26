import socket
import urllib.error
import urllib.request

from fastapi.testclient import TestClient

from memeseeks.phone import Phone, rank_addresses
from memeseeks.server import create_app
from tests.test_albums_api import _setup


def test_addresses_a_phone_could_reach_come_first():
    found = ["172.30.144.1", "10.8.0.5", "192.168.1.156", "169.254.3.3", "127.0.0.1", "8.8.8.8", "not-an-ip"]
    assert rank_addresses(found, default="10.8.0.5") == ["192.168.1.156", "10.8.0.5", "172.30.144.1"]
    assert rank_addresses(["192.168.0.9", "192.168.1.2"], default="192.168.1.2") == ["192.168.1.2", "192.168.0.9"]
    assert rank_addresses([], default=None) == []


class _Servers:
    """Stand-in for starting uvicorn: records what would listen where."""

    def __init__(self, fail=False):
        self.running, self.fail = [], fail

    def start(self, app, host, port):
        if self.fail:
            raise OSError(f"没能在 {host}:{port} 上开启")
        self.running.append((app, host, port))
        return (app, host, port)

    def stop(self, handle):
        self.running.remove(handle)


def _phone(tmp_path, servers, addresses=("192.168.1.156", "172.30.144.1")):
    return Phone(tmp_path / "lib", 8765, make_app=lambda token: ("app", token), start=servers.start,
                 stop=servers.stop, addresses=lambda: list(addresses))


def test_turning_it_on_serves_the_lan_address_with_a_token_and_remembers_it(tmp_path):
    servers = _Servers()
    phone = _phone(tmp_path, servers)
    assert phone.status(local=True)["on"] is False and phone.url() is None
    s = phone.set(True)
    assert servers.running == [(("app", phone.token), "192.168.1.156", 8765)]
    assert s["url"] == f"http://192.168.1.156:8765/?token={phone.token}" and len(phone.token) >= 32
    assert s["addresses"] == ["192.168.1.156", "172.30.144.1"]
    assert "url" not in phone.status(local=False) and "addresses" not in phone.status(local=False)
    phone.set(True, "172.30.144.1")                                     # another address
    assert [r[1] for r in servers.running] == ["172.30.144.1"]
    phone.close()                                                        # the app stops …
    again = _phone(tmp_path, servers)
    again.resume()                                                       # … and comes back on, same address
    assert [r[1] for r in servers.running] == ["172.30.144.1"] and again.status(local=True)["on"] is True
    again.set(False)
    assert servers.running == [] and again.status(local=True)["on"] is False


def test_a_new_token_locks_out_phones_that_scanned_the_old_one(tmp_path):
    servers = _Servers()
    phone = _phone(tmp_path, servers)
    phone.set(True)
    old = phone.token
    phone.rotate()
    assert phone.token != old and servers.running == [(("app", phone.token), "192.168.1.156", 8765)]


def test_it_says_why_when_it_cannot_start(tmp_path):
    no_network = _phone(tmp_path / "a", _Servers(), addresses=())
    assert "局域网地址" in no_network.set(True)["error"]
    busy = _phone(tmp_path / "b", _Servers(fail=True))
    s = busy.set(True)
    assert "没能在" in s["error"] and s["running"] is False and s["url"] is None


def test_the_link_and_the_code_are_for_this_computer_only(tmp_path):
    client, lib, _, _ = _setup(tmp_path)
    servers = _Servers()
    service = client.app.state.service
    phone = Phone(lib.root, 8765, make_app=lambda token: ("app", token), start=servers.start, stop=servers.stop,
                  addresses=lambda: ["192.168.1.156"])
    here = TestClient(create_app(service, phone=phone), base_url="http://127.0.0.1")
    assert here.put("/api/phone", json={"on": True}).json()["url"].startswith("http://192.168.1.156:8765/?token=")
    svg = here.get("/api/phone/qr.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml") and b"<svg" in svg.content
    assert here.put("/api/phone", content='{"on": false}', headers={"Content-Type": "text/plain"}).status_code == 415
    assert here.put("/api/phone", json={"on": "yes"}).status_code == 400
    # the app a phone reaches: needs the token, and never hands it out or changes it
    lan = TestClient(create_app(service, token=phone.token, phone=phone, lan=True), base_url="http://192.168.1.156")
    assert lan.get("/api/phone").status_code == 401
    auth = {"Authorization": f"Bearer {phone.token}"}
    seen = lan.get("/api/phone", headers=auth).json()
    assert seen["on"] is True and "url" not in seen
    assert lan.get("/api/phone/qr.svg", headers=auth).status_code == 403
    assert lan.put("/api/phone", json={"on": False}, headers=auth).status_code == 403
    assert lan.post("/api/phone/rotate", json={}, headers=auth).status_code == 403
    assert TestClient(create_app(service), base_url="http://127.0.0.1").get("/api/phone").json() == {"available": False}


def test_a_real_second_server_needs_the_token(tmp_path):
    client, lib, _, _ = _setup(tmp_path)
    service = client.app.state.service
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    phone = Phone(lib.root, port, make_app=lambda token: create_app(service, token=token, phone=phone, lan=True),
                  addresses=lambda: ["127.0.0.1"])
    try:
        assert phone.set(True)["running"] is True
        base = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            opener.open(f"{base}/api/albums", timeout=5)
            raise AssertionError("answered without the token")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        with opener.open(f"{base}/api/albums?token={phone.token}", timeout=5) as r:
            assert r.status == 200
    finally:
        phone.close()
