# main.py
# ==============================================================================
# 受付係の魂 (ハローワールド・テスト版)
# ==============================================================================
import functions_framework
from flask import jsonify

@functions_framework.http
def article_ingest_service(request):
    """
    呼び出されたら、挨拶を返すだけの、非常にシンプルな関数。
    """
    print("Hello World service was called successfully!")
    return jsonify({
        "status": "ok",
        "message": "Hello from the Article Ingest Service!"
    }), 200
