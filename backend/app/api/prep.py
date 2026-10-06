import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import BomLine, Ingredient, KitchenOrder, OrderLine, PrepRun
from app.services.bom_engine import explode_and_merge, result_to_dict

router = APIRouter(prefix="/prep", tags=["prep"])

_EPS = 1e-6


def _compute_result(order_id: int, db: Session) -> dict:
    """按*当前*定额与结存重算一份结果（仅用于对比脏标或新生成）。"""
    ols = [{"dish_id": l.dish_id, "portions": l.portions}
           for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()]
    bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
           for b in db.scalars(select(BomLine)).all()]
    ings = {i.id: {"code": i.code, "name": i.name, "unit": i.unit, "stock_qty": i.stock_qty}
            for i in db.scalars(select(Ingredient)).all()}
    return result_to_dict(explode_and_merge(ols, bom, ings))


def _stale_report(snapshot: dict, current: dict) -> dict:
    """对比旧单快照与当前定额/结存。只读对比，绝不改快照数字。

    需求对不上 -> 定额或订单已变（qty_changed）；结存对不上 -> 库存已变，
    其引起的缺料差额一并挂在 stock_changed，不误报定额变更。
    """
    snap_lines = {l["ingredient_id"]: l for l in snapshot.get("prep_lines", [])}
    cur_lines = {l["ingredient_id"]: l for l in current.get("prep_lines", [])}

    qty_diffs: list[dict] = []
    stock_diffs: list[dict] = []
    for iid in sorted(snap_lines.keys() | cur_lines.keys()):
        old = snap_lines.get(iid)
        new = cur_lines.get(iid)
        name = (old or new)["ingredient_name"]
        unit = (old or new)["unit"]
        # 需求对不上 -> 定额或订单已变（旧单钉死的是 need_qty）
        if old is None or new is None or abs(old["need_qty"] - new["need_qty"]) > _EPS:
            qty_diffs.append({
                "ingredient_id": iid, "ingredient_name": name, "unit": unit,
                "snapshot_need_qty": None if old is None else old["need_qty"],
                "current_need_qty": None if new is None else new["need_qty"],
                "snapshot_shortage": None if old is None else old["shortage"],
                "current_shortage": None if new is None else new["shortage"],
            })
        # 结存对不上 -> 库存已变；缺料差额由结存变化解释，同样不许改写旧缺料
        if old is not None and new is not None and abs(old["stock_qty"] - new["stock_qty"]) > _EPS:
            stock_diffs.append({
                "ingredient_id": iid, "ingredient_name": name, "unit": unit,
                "snapshot_stock_qty": old["stock_qty"],
                "current_stock_qty": new["stock_qty"],
                "snapshot_shortage": old["shortage"],
                "current_shortage": new["shortage"],
            })

    return {
        "is_stale": bool(qty_diffs or stock_diffs),
        "qty_changed": qty_diffs,   # 定额/订单已与旧单对不上
        "stock_changed": stock_diffs,  # 结存已与旧单对不上
    }


@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    """显式生成：只此一处落新单，按当前定额/结存计算。"""
    order = db.get(KitchenOrder, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    result = _compute_result(order_id, db)
    result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
    run = PrepRun(order_id=order_id, created_at=datetime.utcnow(),
                  result_json=json.dumps(result, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "stale": None, **result}


def _latest_run(order_id: int, db: Session) -> PrepRun | None:
    return db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).first()


@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    """读最近一张备料单。只读快照，绝不落新单、绝不改旧数字。

    无单 -> 200 + exists=false，由前端决定是否提示用户点“生成”。
    旧单与当前定额/结存对不上 -> 原样返回旧数字并带 stale 脏标。
    """
    run = _latest_run(order_id, db)
    if not run:
        return {"exists": False, "id": None, "stale": None}
    snapshot = json.loads(run.result_json)
    stale = _stale_report(snapshot, _compute_result(order_id, db))
    return {"id": run.id, "exists": True, "created_at": run.created_at.isoformat(),
            "stale": stale, **snapshot}


@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    """缺料便利贴：同样钉死旧单快照，缺料数字不随当前结存改写。"""
    run = _latest_run(order_id, db)
    if not run:
        return {"order_id": order_id, "exists": False, "stale": None,
                "shortages": [], "stats": {}}
    snapshot = json.loads(run.result_json)
    stale = _stale_report(snapshot, _compute_result(order_id, db))
    return {"order_id": order_id, "exists": True, "id": run.id, "stale": stale,
            "shortages": snapshot.get("shortages", []), "stats": snapshot.get("stats", {})}
