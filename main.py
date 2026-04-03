import os
from pathlib import Path

# 今実行しているファイルの場所を基準にする
BASE_DIR = Path(__file__).resolve().parent

from fastapi.responses import FileResponse
import os

import pandas as pd
import numpy as np
import csv
import os
import uuid
import urllib.parse
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os  # 👈 これが必要！
from fastapi import FastAPI
from fastapi.responses import FileResponse  # 👈 これも必要！

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSV読み込みと正規化
csv_path = "spots.csv"
df_spots = pd.read_csv(csv_path)
df_spots.fillna(0, inplace=True)

for col in ['天空率(%)', '緑視率(%)', '複雑性(D)', '推定騒音(dB)']:
    c_min = df_spots[col].min()
    c_max = df_spots[col].max()
    if c_max > c_min:
        df_spots[f'{col}_norm'] = (df_spots[col] - c_min) / (c_max - c_min) * 100
    else:
        df_spots[f'{col}_norm'] = 50.0

class DiagnosticRequest(BaseModel):
    origin: str
    living_status: str
    stresses: List[str]
    words: List[str]
    stay_style: str

class FeedbackRequest(BaseModel):
    session_id: str
    rating: int
    comment: str

LOG_FILE = "repace_experiment_logs.csv"

@app.post("/api/diagnose_and_recommend")
def diagnose_and_recommend(request: DiagnosticRequest):
    session_id = str(uuid.uuid4())
    
    # 理想バランス計算
    target_sky = 50.0; target_green = 50.0; target_simple = 50.0; target_quiet = 50.0
    
    if request.origin == "地方": target_green += 5.0; target_simple += 10.0
    else: target_quiet += 10.0
    if request.living_status == "実家暮らし": target_quiet += 10.0
    else: target_sky += 10.0

    stress_weight = 30.0 / max(1, len(request.stresses)) if request.stresses else 0.0
    for s in request.stresses:
        if s in ["情報過多", "マルチタスク", "他者の目線"]: target_simple += stress_weight
        elif s in ["人混み", "満員電車"]: target_simple += stress_weight/2; target_quiet += stress_weight/2
        elif s in ["閉塞感", "息苦しさ", "ビル群", "空の狭さ"]: target_sky += stress_weight
        elif s in ["人工物", "無機質", "ホームシック"]: target_green += stress_weight
        elif s in ["騒音", "焦燥感", "時間の流れ", "早いスピード感"]: target_quiet += stress_weight

    word_weight = 30.0 / max(1, len(request.words)) if request.words else 0.0
    for w in request.words:
        if w in ["自然に触れる", "木漏れ日", "生命力", "土の匂い"]: target_green += word_weight
        elif w in ["空の広さ", "開放感", "深呼吸", "抜け感"]: target_sky += word_weight
        elif w in ["静寂", "一人の時間", "没入", "外部との遮断"]: target_quiet += word_weight
        elif w in ["余白", "何もしない", "思考の整理", "リセット"]: target_simple += word_weight

    if request.stay_style == "歩きながら頭を整理したい": target_simple += 15.0; target_green += 10.0
    elif request.stay_style == "座って一息つきたい": target_quiet += 15.0; target_simple += 10.0
    elif request.stay_style == "ただ景色を眺めたい": target_sky += 20.0
    elif request.stay_style == "目を閉じて音を遮断したい": target_quiet += 25.0; target_simple += 15.0

    target_sky = max(0.0, min(100.0, target_sky))
    target_green = max(0.0, min(100.0, target_green))
    target_simple = max(0.0, min(100.0, target_simple))
    target_quiet = max(0.0, min(100.0, target_quiet))

    # 距離計算
    recommendations = []
    for _, row in df_spots.iterrows():
        dist = np.sqrt((row['天空率(%)_norm'] - target_sky)**2 + (row['緑視率(%)_norm'] - target_green)**2 + (row['複雑性(D)_norm'] - target_simple)**2 + (row['推定騒音(dB)_norm'] - target_quiet)**2)
        match_rate = max(0.0, 100.0 - (dist / 2.0))
        img_url = str(row['画像URL']) if '画像URL' in df_spots.columns and row['画像URL'] != 0 else f"https://picsum.photos/seed/{urllib.parse.quote(str(row['地点名']))}/600/400"
        recommendations.append({"name": str(row['地点名']), "match_rate": round(match_rate, 1), "image_url": img_url, "category": str(row['カテゴリ']), "context": str(row['備考・コンテキスト'])})

    recommendations.sort(key=lambda x: x["match_rate"], reverse=True)
    top_3 = recommendations[:3]

    # 💡 統合ログへの書き込み（TOP3すべての情報を含める）
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", encoding="utf_8_sig", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["SessionID", "日時", "出身", "居住", "ストレス", "欲求", "過ごし方", "理想_空", "理想_緑", "理想_整", "理想_静", "推薦1位", "適合1", "推薦2位", "適合2", "推薦3位", "適合3", "評価(星)", "コメント"])
        writer.writerow([
            session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            request.origin, request.living_status, "|".join(request.stresses), "|".join(request.words), request.stay_style,
            f"{target_sky:.1f}", f"{target_green:.1f}", f"{target_simple:.1f}", f"{target_quiet:.1f}",
            top_3[0]["name"], top_3[0]["match_rate"],
            top_3[1]["name"] if len(top_3) > 1 else "", top_3[1]["match_rate"] if len(top_3) > 1 else "",
            top_3[2]["name"] if len(top_3) > 2 else "", top_3[2]["match_rate"] if len(top_3) > 2 else "",
            "", "" 
        ])

    feedback_msg = f"【理想バランス診断】\n空 {target_sky:.1f}% / 緑 {target_green:.1f}% / 整 {target_simple:.1f}% / 静 {target_quiet:.1f}%\n\nこの数値に最も近い順に提案します。"
    return {"session_id": session_id, "diagnosis_message": feedback_msg, "recommended_spots": top_3}

@app.post("/api/feedback")
def save_feedback(request: FeedbackRequest):
    df_log = pd.read_csv(LOG_FILE)
    df_log.loc[df_log['SessionID'] == request.session_id, '評価(星)'] = request.rating
    df_log.loc[df_log['SessionID'] == request.session_id, 'コメント'] = request.comment
    df_log.to_csv(LOG_FILE, index=False, encoding="utf_8_sig")
    return {"status": "success"}

# 💡 URLのトップ（/）にアクセスした時、自動で index.html を表示させる設定
@app.get("/")
async def read_index():
    # main.py と同じフォルダにある index.html を探して表示する
    current_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(current_dir, "index.html")
    
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        return {"error": "index.html が見つかりません。フォルダ構成を確認してください。"}
    
if __name__ == "__main__":
    import uvicorn
    import os
    # Renderが指定するポート番号を自動で受け取る魔法
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)