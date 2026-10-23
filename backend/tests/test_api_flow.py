from __future__ import annotations

from app.services.seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo


async def _login(client, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_register_login_and_me(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123", "nickname": "新用户"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]

    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123", "nickname": "重复"},
    )
    assert duplicate.status_code == 409

    bad_login = await client.post(
        "/api/v1/auth/login", json={"email": "new@example.com", "password": "wrong"}
    )
    assert bad_login.status_code == 401


async def test_requires_authentication(client):
    response = await client.get("/api/v1/feed")
    assert response.status_code == 401


async def test_demo_feed_watchlist_and_stock_detail(client, db_session):
    await seed_demo(db_session)
    token = await _login(client, DEMO_EMAIL, DEMO_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    feed = await client.get(
        "/api/v1/feed?scope=following&sort=smart&window=30d&limit=10", headers=headers
    )
    assert feed.status_code == 200, feed.text
    payload = feed.json()
    assert len(payload["items"]) >= 5
    first = payload["items"][0]
    assert first["summary"]
    assert first["display_score"] is not None
    assert first["author"]["followed"] is True
    assert first["published_at"].endswith("Z")

    discover = await client.get(
        "/api/v1/feed?scope=discover&sort=hot&window=72h&limit=3", headers=headers
    )
    assert discover.status_code == 200
    assert len(discover.json()["items"]) == 3

    watchlist = await client.get("/api/v1/watchlist", headers=headers)
    assert watchlist.status_code == 200, watchlist.text
    items = watchlist.json()
    assert len(items) == 3
    assert all(item["score"]["conclusion"] for item in items)

    detail = await client.get("/api/v1/stocks/600519.SH?window=30d", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["score"]["report_count"] >= 1
    assert body["score"]["final_score"] > 0
    assert body["score"]["total_points"] == body["score"]["display_score"]
    assert body["score"]["relation_scores"]
    assert body["score"]["evidence"]["level"] in {"direct", "industry", "macro"}
    assert body["score"]["display_label"] in {"综合得分", "宏观参考"}
    assert body["score"]["relation_counts"]["stock"] >= 1
    assert body["score"]["max_age_days"] == 90
    assert body["related_reports"]

    report_id = payload["items"][0]["id"]
    report = await client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert report.status_code == 200
    assert report.json()["key_points"]

    interaction = await client.post(
        f"/api/v1/reports/{report_id}/interaction",
        json={"read": True, "saved": True},
        headers=headers,
    )
    assert interaction.status_code == 200
    assert interaction.json()["saved"] is True

    hidden = await client.post(
        f"/api/v1/reports/{report_id}/interaction",
        json={"hidden": True},
        headers=headers,
    )
    assert hidden.status_code == 200

    feed_after_hide = await client.get(
        "/api/v1/feed?scope=following&sort=smart&window=30d&limit=10", headers=headers
    )
    assert report_id not in [item["id"] for item in feed_after_hide.json()["items"]]


async def test_stock_history_feedback_and_digest(client, db_session):
    await seed_demo(db_session)
    token = await _login(client, DEMO_EMAIL, DEMO_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    detail = await client.get(
        "/api/v1/stocks/600519.SH?window=30d", headers=headers
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    report_id = body["score"]["breakdown"][0]["report_id"]
    before_count = body["score"]["report_count"]
    assert before_count >= 1

    history = await client.get(
        "/api/v1/stocks/600519.SH/history?scope=hybrid&window=30d&days=30",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    history_body = history.json()
    assert history_body["scope"] == "hybrid"
    assert history_body["points"]
    assert set(history_body["deltas"]) == {"1d", "7d", "30d"}

    excluded = await client.post(
        "/api/v1/stocks/600519.SH/feedback",
        json={"report_id": report_id},
        headers=headers,
    )
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["excluded"] is True

    after_feedback = await client.get(
        "/api/v1/stocks/600519.SH?window=30d", headers=headers
    )
    after_body = after_feedback.json()
    assert after_body["score"]["report_count"] == before_count - 1
    assert report_id not in {
        item["report_id"] for item in after_body["score"]["breakdown"]
    }

    restored = await client.delete(
        f"/api/v1/stocks/600519.SH/feedback/{report_id}", headers=headers
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["excluded"] is False

    after_restore = await client.get(
        "/api/v1/stocks/600519.SH?window=30d", headers=headers
    )
    assert after_restore.json()["score"]["report_count"] == before_count

    digest = await client.get(
        "/api/v1/digest?scope=hybrid&window=30d", headers=headers
    )
    assert digest.status_code == 200, digest.text
    digest_body = digest.json()
    assert digest_body["scope"] == "hybrid"
    assert {"followed_updates", "watchlist_changes", "evidence_gaps"} <= set(
        digest_body
    )
    assert digest_body["has_content"] is True


async def test_author_follow_flow(client, db_session):
    await seed_demo(db_session)
    token = await _login(client, DEMO_EMAIL, DEMO_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    authors = await client.get("/api/v1/authors", headers=headers)
    assert authors.status_code == 200
    author_id = authors.json()["items"][0]["id"]

    unfollow = await client.delete(f"/api/v1/authors/{author_id}/follow", headers=headers)
    assert unfollow.status_code == 200

    follow = await client.post(
        f"/api/v1/authors/{author_id}/follow",
        json={"weight": 1.5, "notify": True},
        headers=headers,
    )
    assert follow.status_code == 200
    assert follow.json()["weight"] == 1.5

    detail = await client.get(f"/api/v1/authors/{author_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["report_count"] >= 1
