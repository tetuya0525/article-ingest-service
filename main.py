# main.py (Hello World Test)
import functions_framework
from flask import jsonify
import os

@functions_framework.http
def article_ingest_service(request):
    """
    デプロイプロセスを検証するための、最もシンプルなサービス。
    呼び出されたら、挨拶を返すだけ。
    """
    print("Hello World service was called successfully!")
    return jsonify({
        "status": "ok",
        "message": "Hello from the simplest service!"
    }), 200
