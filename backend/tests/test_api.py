from uuid import UUID

from sqlalchemy import select

from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import DEFAULT_STAGES
from farq.privacy import hash_user_id
from farq.storage.tables import CaseRow

VIDEO = ("clip.mp4", b"fake video bytes", "video/mp4")


def test_upload_creates_case_stores_media_and_queues_it(client, media, queued):
    response = client.post("/cases", files={"file": VIDEO}, data={"money_sent": "true"})
    assert response.status_code == 202
    body = response.json()
    assert body["duplicate"] is False
    assert queued == [UUID(body["case_id"])]
    assert media.objects == {f"cases/{body['case_id']}/original.mp4": b"fake video bytes"}


def test_same_message_id_is_one_case(client, queued):
    first = client.post("/cases", files={"file": VIDEO}, data={"message_id": "m1"}).json()
    second = client.post("/cases", files={"file": VIDEO}, data={"message_id": "m1"}).json()
    assert (second["case_id"], second["duplicate"]) == (first["case_id"], True)
    assert len(queued) == 1


def test_missing_or_wrong_api_key_is_rejected(client):
    for headers in ({"X-API-Key": ""}, {"X-API-Key": "wrong"}):
        assert client.post("/cases", files={"file": VIDEO}, headers=headers).status_code == 401
        assert client.get("/cases/x", headers=headers).status_code == 401


def test_unsupported_file_type_is_rejected(client):
    response = client.post("/cases", files={"file": ("run.exe", b"MZ", "application/x-msdownload")})
    assert response.status_code == 415


def test_empty_file_is_rejected(client):
    assert client.post("/cases", files={"file": ("clip.mp4", b"", "video/mp4")}).status_code == 400


def test_too_large_file_is_rejected(client, queued):
    big = b"x" * (1024 * 1024 + 1)  # MAX_UPLOAD_MB is 1 in tests
    response = client.post("/cases", files={"file": ("clip.mp4", big, "video/mp4")})
    assert response.status_code == 413
    assert queued == []


def test_raw_user_id_is_never_stored(client, session):
    client.post("/cases", files={"file": VIDEO})
    row = session.scalars(select(CaseRow)).one()
    assert row.user_hash == hash_user_id("local-upload", "test-hash-key")
    assert "local-upload" not in row.user_hash


def test_case_view_shows_reply_without_raw_details(
    client, repo, rules, media, queued, sample_video
):
    upload = ("clip.mp4", sample_video, "video/mp4")
    case_id = client.post("/cases", files={"file": upload}).json()["case_id"]
    assert client.get(f"/cases/{case_id}/debug").json()["status"] == "received"

    run_pipeline(queued[0], repo, rules, media)
    view = client.get(f"/cases/{case_id}/debug").json()
    assert view["status"] == "decided"
    assert view["verdict"] == "NOT VERIFIED"
    assert "does not mean it is genuine" in view["reply_text"]
    assert [s["stage"] for s in view["stages"]][-1] == "decide"
    assert all("details" not in e for e in view["evidence"])
    assert {a["kind"] for a in view["artifacts"]} >= {"media_info", "keyframes", "audio_16k"}
    assert all("data" not in a for a in view["artifacts"])


def test_unknown_case_is_404(client):
    assert client.get("/cases/00000000-0000-0000-0000-000000000000").status_code == 404


def test_latency_metrics_come_from_real_runs(client, repo, rules, media, queued):
    empty = client.get("/metrics/latency").json()
    assert empty["cases"] == 0
    assert empty["end_to_end"] == {"known_fake": None, "new_video": None}

    client.post("/cases", files={"file": VIDEO})
    run_pipeline(queued[0], repo, rules, media)
    report = client.get("/metrics/latency").json()
    assert report["cases"] == 1
    assert report["end_to_end"]["new_video"]["count"] == 1
    assert report["end_to_end"]["known_fake"] is None
    assert set(report["stages"]) == {s.name for s in DEFAULT_STAGES} | {"decide"}
    assert report["targets_ms"] == {"known_fake": 10_000, "new_video": 60_000}
