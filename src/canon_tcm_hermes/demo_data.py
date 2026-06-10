from __future__ import annotations
from pathlib import Path
import pandas as pd

def make_demo(path: str | Path = "data/demo/shanghan_six_formula_demo.xlsx") -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"book":"伤寒论","volume":"辨太阳病脉证并治","chapter":"太阳病","content":"太阳病，头痛发热，身疼腰痛，骨节疼痛，恶风，无汗而喘者，麻黄汤主之。麻黄三两桂枝二两杏仁七十枚甘草一两，右四味，以水九升，煮取二升半，去滓，温服八合。"},
        {"book":"伤寒论","volume":"辨太阳病脉证并治","chapter":"太阳病","content":"太阳中风，阳浮而阴弱，阳浮者，热自发，阴弱者，汗自出，桂枝汤主之。"},
        {"book":"本草经","volume":"上品","chapter":"麻黄","content":"麻黄，味苦温，主中风伤寒头痛，温疟，发表出汗，去邪热气。"},
        {"book":"脉经","volume":"卷一","chapter":"浮脉","content":"浮脉，举之有余，按之不足，浮为风，为虚。"},
        {"book":"临证指南医案","volume":"太阳","chapter":"医案","content":"王姓妇，年三十，初诊发热恶寒无汗而喘，予投麻黄汤一剂，翌日热退而愈。"},
        {"book":"伤寒注解","volume":"太阳","chapter":"麻黄汤注","content":"太阳病，头痛发热，无汗而喘者，麻黄汤主之。注曰：此表实无汗，故以麻黄发之。"},
        {"book":"汤头歌诀","volume":"发表之剂","chapter":"麻黄汤","content":"麻黄汤中用桂枝，杏仁甘草四般施。"},
        {"book":"素问","volume":"至真要大论","chapter":"病机十九条","content":"诸风掉眩，皆属于肝。"},
    ]
    pd.DataFrame(rows).to_excel(path, index=False)
    return path

if __name__ == "__main__":
    print(make_demo())
