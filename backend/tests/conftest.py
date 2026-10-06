import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import BomLine, Dish, Ingredient, KitchenOrder, OrderLine


@pytest.fixture()
def db_session():
    # 纯内存库；不触发 app 的 lifespan（不连 postgres、不跑 seed）
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Testing = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Testing()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    # 不用 with：跳过 lifespan，避免对真实 postgres 建表/seed
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db_session):
    """红烧肉 40 份 × 0.25kg/份 = 需 10kg；结存 8kg → 缺 2kg。"""
    dish = Dish(code="D-HS", name="红烧肉套餐", portion_unit="份")
    meat = Ingredient(code="I-PR", name="五花肉", unit="kg", stock_qty=8.0)
    db_session.add_all([dish, meat])
    db_session.flush()
    order = KitchenOrder(code="KO-1", outlet="城西门店", status="open")
    db_session.add(order)
    db_session.flush()
    db_session.add(BomLine(dish_id=dish.id, ingredient_id=meat.id, qty_per_portion=0.25))
    db_session.add(OrderLine(order_id=order.id, dish_id=dish.id, portions=40))
    db_session.commit()
    return {"order_id": order.id, "dish_id": dish.id, "ingredient_id": meat.id}
