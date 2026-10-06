"""备料单钉死语义测试：读不落单、改定额/结存只亮脏标、重新生成才出新单。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.api import prep
from app.models.models import BomLine, Dish, Ingredient, KitchenOrder, OrderLine, PrepRun


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    db = TestingSession()
    dish = Dish(code="D1", name="测试菜", portion_unit="份")
    ing = Ingredient(code="I1", name="肉", unit="kg", stock_qty=1.0)
    db.add_all([dish, ing])
    db.flush()
    db.add_all([
        BomLine(dish_id=dish.id, ingredient_id=ing.id, qty_per_portion=0.2),
    ])
    order = KitchenOrder(code="KO-1", outlet="测试门店", status="open")
    db.add(order)
    db.flush()
    db.add(OrderLine(order_id=order.id, dish_id=dish.id, portions=10))
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(prep.router, prefix="/api")

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_reading_latest_without_run_does_not_create_one(client, db_session):
    res = client.get("/api/prep/latest?order_id=1")
    assert res.status_code == 200
    assert res.json()["exists"] is False
    # 关键：读旧单这个动作不得落一张新单
    assert len(db_session.scalars(select(PrepRun)).all()) == 0

    res2 = client.get("/api/prep/shortages?order_id=1")
    assert res2.json()["exists"] is False
    assert res2.json()["shortages"] == []
    assert len(db_session.scalars(select(PrepRun)).all()) == 0


def test_bom_change_marks_stale_but_keeps_snapshot_numbers(client, db_session):
    run = client.post("/api/prep/run?order_id=1").json()
    assert run["prep_lines"][0]["need_qty"] == 2.0  # 10 × 0.2

    # 改定额：0.2 -> 0.5
    bom = db_session.scalars(select(BomLine)).first()
    bom.qty_per_portion = 0.5
    db_session.commit()

    res = client.get("/api/prep/latest?order_id=1").json()
    # 旧单数字必须钉死
    assert res["exists"] is True
    assert res["id"] == run["id"]
    assert res["prep_lines"][0]["need_qty"] == 2.0
    assert res["shortages"][0]["shortage"] == 1.0
    # 只允许亮脏标
    assert res["stale"]["is_stale"] is True
    assert len(res["stale"]["qty_changed"]) == 1
    diff = res["stale"]["qty_changed"][0]
    assert diff["snapshot_need_qty"] == 2.0
    assert diff["current_need_qty"] == 5.0
    # 读旧单没有再落新单
    assert len(db_session.scalars(select(PrepRun)).all()) == 1

    sh = client.get("/api/prep/shortages?order_id=1").json()
    assert sh["shortages"][0]["shortage"] == 1.0  # 缺料数字不被改写
    assert sh["stale"]["is_stale"] is True
    assert len(db_session.scalars(select(PrepRun)).all()) == 1


def test_stock_change_marks_stale_without_touching_snapshot(client, db_session):
    client.post("/api/prep/run?order_id=1")
    # 结存 1.0 -> 4.0：当前已不缺料，但旧单缺料必须保留
    ing = db_session.scalars(select(Ingredient)).first()
    ing.stock_qty = 4.0
    db_session.commit()

    res = client.get("/api/prep/latest?order_id=1").json()
    line = res["prep_lines"][0]
    assert line["need_qty"] == 2.0
    assert line["shortage"] == 1.0  # 旧缺料钉死，不被新结存冲成 0
    assert res["stale"]["is_stale"] is True
    assert res["stale"]["qty_changed"] == []
    assert len(res["stale"]["stock_changed"]) == 1
    sc = res["stale"]["stock_changed"][0]
    assert sc["snapshot_stock_qty"] == 1.0
    assert sc["current_stock_qty"] == 4.0
    # 结存变化解释缺料差额：旧缺 1.0 钉死，当前已为 0
    assert sc["snapshot_shortage"] == 1.0
    assert sc["current_shortage"] == 0.0


def test_regenerate_produces_new_run_with_new_quotas(client, db_session):
    first = client.post("/api/prep/run?order_id=1").json()
    bom = db_session.scalars(select(BomLine)).first()
    bom.qty_per_portion = 0.5
    db_session.commit()

    # 旧单仍脏
    old = client.get("/api/prep/latest?order_id=1").json()
    assert old["stale"]["is_stale"] is True

    # 显式重新生成：新点生成才按新定额出新单
    second = client.post("/api/prep/run?order_id=1").json()
    assert second["id"] != first["id"]
    assert second["prep_lines"][0]["need_qty"] == 5.0

    runs = db_session.scalars(select(PrepRun).order_by(PrepRun.id)).all()
    assert len(runs) == 2  # 旧单保留，新单另落
    latest = client.get("/api/prep/latest?order_id=1").json()
    assert latest["id"] == second["id"]
    assert latest["prep_lines"][0]["need_qty"] == 5.0
    assert latest["stale"]["is_stale"] is False
