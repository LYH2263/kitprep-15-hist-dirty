import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import BomLine, Ingredient, KitchenOrder, OrderLine, PrepRun
from app.services.bom_engine import bom_signature, explode_and_merge, result_to_dict

router = APIRouter(prefix="/prep", tags=["prep"])


def _load_inputs(db: Session, order_id: int):
    """读取某订单生成备料单所需的当下输入（订单、订单行、定额）。"""
    order = db.get(KitchenOrder, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    ols = [{"dish_id": l.dish_id, "portions": l.portions}
           for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()]
    bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
           for b in db.scalars(select(BomLine)).all()]
    return order, ols, bom


def _load_ingredients(db: Session) -> dict:
    return {i.id: {"code": i.code, "name": i.name, "unit": i.unit, "stock_qty": i.stock_qty}
            for i in db.scalars(select(Ingredient)).all()}


def _snapshot(run: PrepRun, dirty: bool, dirty_reasons: list[str]) -> dict:
    """旧单/新单统一出口：只返回落库快照，绝不重算其中任何数字。"""
    data = json.loads(run.result_json)
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "dirty": dirty,
        "dirty_reasons": dirty_reasons,
        **data,
    }


@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    """按当下定额与结存生成一张新单并落库。只有这个动作会写 prep_runs。"""
    order, ols, bom = _load_inputs(db, order_id)
    ings = _load_ingredients(db)
    result = result_to_dict(explode_and_merge(ols, bom, ings))
    result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
    run = PrepRun(
        order_id=order_id,
        created_at=datetime.utcnow(),
        bom_signature=bom_signature(ols, bom),
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _snapshot(run, dirty=False, dirty_reasons=[])


@router.get("/runs")
def list_runs(order_id: int, db: Session = Depends(get_db)):
    """某订单的历史备料单清单，供切换查看（纯读，不生成）。"""
    if not db.get(KitchenOrder, order_id):
        raise HTTPException(404, "订单不存在")
    runs = db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
             "dirty": _is_dirty(db, r)[0]} for r in runs]


@router.get("/run/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    """读取任意一张已生成的备料单。返回的是生成当时的快照；定额对不上只亮脏标。"""
    run = db.get(PrepRun, run_id)
    if not run:
        raise HTTPException(404, "备料单不存在")
    dirty, reasons = _is_dirty(db, run)
    return _snapshot(run, dirty, reasons)


@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    """读取该订单最近一张备料单（纯读）。从未生成过时返回 404，绝不顺手生成新单。"""
    if not db.get(KitchenOrder, order_id):
        raise HTTPException(404, "订单不存在")
    run = db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).first()
    if not run:
        raise HTTPException(404, "尚未生成备料单")
    dirty, reasons = _is_dirty(db, run)
    return _snapshot(run, dirty, reasons)


@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    """缺料便利贴：取最近一张单的落库缺料，不重算；无单则 404。"""
    data = latest(order_id=order_id, db=db)
    return {"order_id": order_id, "run_id": data["id"], "dirty": data["dirty"],
            "dirty_reasons": data["dirty_reasons"],
            "shortages": data.get("shortages", []), "stats": data.get("stats", {})}


def _is_dirty(db: Session, run: PrepRun) -> tuple[bool, list[str]]:
    """比对生成时指纹与当下定额×订单构成。只出标记，绝不动快照里的数字。

    历史单（指纹列为空）无法逐行核对时，保守判脏并提示。结存变化不判脏。
    """
    if not run.bom_signature:
        return True, ["旧单缺少定额指纹，无法确认与当下定额一致"]
    ols = [{"dish_id": l.dish_id, "portions": l.portions}
           for l in db.scalars(select(OrderLine).where(OrderLine.order_id == run.order_id)).all()]
    bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
           for b in db.scalars(select(BomLine)).all()]
    if bom_signature(ols, bom) != run.bom_signature:
        return True, ["定额或订单构成已与本单生成时不一致；数字仍为生成当时快照，重新生成才会按新定额出新单"]
    return False, []
