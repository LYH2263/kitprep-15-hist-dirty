"""Central kitchen BOM explode: order lines × BOM qty, merge ingredients, shortage = need - stock.

结果中的 need/stock/shortage 都是生成时刻的快照值；旧单只读，不允许用当下定额或结存重算。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

@dataclass
class NeedLine:
    ingredient_id: int
    ingredient_code: str
    ingredient_name: str
    unit: str
    need_qty: float
    stock_qty: float
    shortage: float
    # 生成当时该行所用的定额（每个原料跨菜品合计后的总单位用量），仅用于展示/核对
    qty_per_portion: float = 0.0

def explode_and_merge(
    order_lines: list[dict],
    bom_lines: list[dict],
    ingredients: dict[int, dict],
) -> list[NeedLine]:
    """order_lines: dish_id, portions; bom_lines: dish_id, ingredient_id, qty_per_portion."""
    need: dict[int, float] = {}
    rate: dict[int, float] = {}
    for ol in order_lines:
        for bl in bom_lines:
            if bl["dish_id"] != ol["dish_id"]:
                continue
            iid = bl["ingredient_id"]
            qpp = float(bl["qty_per_portion"])
            need[iid] = need.get(iid, 0.0) + ol["portions"] * qpp
            rate[iid] = rate.get(iid, 0.0) + qpp
    lines: list[NeedLine] = []
    for iid, qty in sorted(need.items()):
        ing = ingredients[iid]
        stock = float(ing.get("stock_qty", 0))
        shortage = max(0.0, qty - stock)
        lines.append(NeedLine(
            ingredient_id=iid,
            ingredient_code=ing["code"],
            ingredient_name=ing["name"],
            unit=ing.get("unit", ""),
            need_qty=round(qty, 3),
            stock_qty=round(stock, 3),
            shortage=round(shortage, 3),
            qty_per_portion=round(rate.get(iid, 0.0), 6),
        ))
    return lines

def result_to_dict(lines: list[NeedLine]) -> dict:
    return {
        "prep_lines": [asdict(l) for l in lines],
        "shortages": [asdict(l) for l in lines if l.shortage > 0],
        "stats": {
            "ingredient_count": len(lines),
            "shortage_count": sum(1 for l in lines if l.shortage > 0),
            "total_shortage_qty": round(sum(l.shortage for l in lines), 3),
        },
    }

def bom_signature(order_lines: list[dict], bom_lines: list[dict]) -> str:
    """定额 × 订单构成指纹。

    仅覆盖影响需求量的输入：订单菜品/份数与每张定额行（菜品→原料→单位用量）。
    结存（stock_qty）不参与——结存变动只影响当下重算，不应把旧单判脏。
    """
    payload = {
        "orders": sorted(
            ((int(ol["dish_id"]), int(ol["portions"])) for ol in order_lines)
        ),
        "bom": sorted(
            (int(bl["dish_id"]), int(bl["ingredient_id"]), round(float(bl["qty_per_portion"]), 6))
            for bl in bom_lines
        ),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
