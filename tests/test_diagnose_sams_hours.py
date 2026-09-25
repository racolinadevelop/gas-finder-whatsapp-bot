from scripts import diagnose_sams_hours as diagnostic


def test_missing_hours_are_unknown_not_closed():
    assert diagnostic.format_status({}).startswith("UNKNOWN")
    assert diagnostic.format_status({"openNow": False}) == "CLOSED"
    assert diagnostic.format_status({"openNow": True}) == "OPEN"


def test_fetches_candidates_with_hours_without_open_now_filter(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"places": [{"id": "station-id"}]}

    def fake_post(url, headers, json, timeout):
        captured.update(
            {"url": url, "headers": headers, "payload": json, "timeout": timeout}
        )
        return FakeResponse()

    monkeypatch.setattr(diagnostic.httpx, "post", fake_post)

    assert diagnostic.fetch_candidates("test-key") == [{"id": "station-id"}]
    assert "currentOpeningHours" in captured["headers"]["X-Goog-FieldMask"]
    assert "regularOpeningHours" in captured["headers"]["X-Goog-FieldMask"]
    assert captured["payload"]["textQuery"] == diagnostic.QUERY
    assert "openNow" not in captured["payload"]
    assert captured["payload"]["pageSize"] == 5
