"""旧单必须钉死生成当时的需求与缺料：改定额/结存后重读旧单，只许亮脏标，不许改数字。"""
from app.models.models import BomLine, Ingredient, PrepRun
from sqlalchemy import select


def _line(resp, ingredient_id):
    return next(l for l in resp.json()["prep_lines"] if l["ingredient_id"] == ingredient_id)


def test_generate_then_change_bom_old_run_numbers_frozen_and_dirty(client, seeded, db_session):
    iid = seeded["ingredient_id"]

    r = client.post("/api/prep/run", params={"order_id": seeded["order_id"]})
    assert r.status_code == 200
    run1 = r.json()
    assert run1["dirty"] is False
    assert _line(r, iid)["need_qty"] == 10.0
    assert _line(r, iid)["shortage"] == 2.0

    # 定额 0.25 → 0.40：新定额下需求应为 16kg
    bl = db_session.scalars(select(BomLine)).first()
    bl.qty_per_portion = 0.40
    db_session.commit()

    # 读旧单：数字钉死，只亮脏标
    r = client.get("/api/prep/latest", params={"order_id": seeded["order_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == run1["id"]
    assert body["dirty"] is True
    assert body["dirty_reasons"]
    assert _line(r, iid)["need_qty"] == 10.0
    assert _line(r, iid)["shortage"] == 2.0

    # 缺料便利贴同样钉死
    r = client.get("/api/prep/shortages", params={"order_id": seeded["order_id"]})
    assert r.status_code == 200
    assert r.json()["dirty"] is True
    short = next(s for s in r.json()["shortages"] if s["ingredient_id"] == iid)
    assert short["need_qty"] == 10.0
    assert short["shortage"] == 2.0

    # 整个读取过程没有新增任何备料单
    assert db_session.query(PrepRun).count() == 1


def test_get_run_by_id_is_also_readonly(client, seeded, db_session):
    iid = seeded["ingredient_id"]
    rid = client.post("/api/prep/run", params={"order_id": seeded["order_id"]}).json()["id"]

    db_session.scalars(select(BomLine)).first().qty_per_portion = 0.40
    db_session.commit()

    r = client.get(f"/api/prep/run/{rid}")
    assert r.status_code == 200
    assert r.json()["dirty"] is True
    assert _line(r, iid)["need_qty"] == 10.0
    assert db_session.query(PrepRun).count() == 1


def test_stock_change_freezes_numbers_without_dirty_flag(client, seeded, db_session):
    """结存变化不改旧数字；结存不参与定额指纹，因此不亮脏标（重生成才体现新结存）。"""
    iid = seeded["ingredient_id"]
    r = client.post("/api/prep/run", params={"order_id": seeded["order_id"]})
    assert _line(r, iid)["stock_qty"] == 8.0

    db_session.get(Ingredient, iid).stock_qty = 3.0
    db_session.commit()

    r = client.get("/api/prep/latest", params={"order_id": seeded["order_id"]})
    assert r.status_code == 200
    assert r.json()["dirty"] is False
    assert _line(r, iid)["stock_qty"] == 8.0   # 钉死旧结存
    assert _line(r, iid)["shortage"] == 2.0    # 旧缺料不随结存重算
    assert db_session.query(PrepRun).count() == 1


def test_latest_without_run_returns_404_and_creates_nothing(client, seeded, db_session):
    r = client.get("/api/prep/latest", params={"order_id": seeded["order_id"]})
    assert r.status_code == 404
    r = client.get("/api/prep/shortages", params={"order_id": seeded["order_id"]})
    assert r.status_code == 404
    assert db_session.query(PrepRun).count() == 0


def test_regenerate_uses_new_bom_and_keeps_old_run(client, seeded, db_session):
    iid = seeded["ingredient_id"]
    first = client.post("/api/prep/run", params={"order_id": seeded["order_id"]}).json()

    db_session.scalars(select(BomLine)).first().qty_per_portion = 0.40
    db_session.commit()

    second = client.post("/api/prep/run", params={"order_id": seeded["order_id"]}).json()
    assert second["id"] != first["id"]
    assert second["dirty"] is False
    assert _line_by_id(second, iid)["need_qty"] == 16.0  # 40 × 0.40
    assert _line_by_id(second, iid)["shortage"] == 8.0

    # 旧单仍在，仍是旧数字、仍脏
    r = client.get(f"/api/prep/run/{first['id']}")
    assert r.json()["dirty"] is True
    assert _line(r, iid)["need_qty"] == 10.0

    runs = client.get("/api/prep/runs", params={"order_id": seeded["order_id"]}).json()
    assert [x["id"] for x in runs] == [second["id"], first["id"]]
    assert runs[0]["dirty"] is False
    assert runs[1]["dirty"] is True


def _line_by_id(body, ingredient_id):
    return next(l for l in body["prep_lines"] if l["ingredient_id"] == ingredient_id)
