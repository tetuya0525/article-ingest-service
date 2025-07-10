# main.py
# ==============================================================================
# Memory Library - Article Ingest Service
# Role:         Receives a validated JSON object from the API Gateway,
#               separates it into article and dictionary data, and saves
#               them to their respective staging collections.
# Version:      2.0 (Production Ready)
# Author:       心理 (Thinking Partner)
# Last Updated: 2025-07-11
# ==============================================================================

import functions_framework
from flask import request, jsonify
import os
import traceback
import requests
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

# --- 定数 (Constants) ---
LOG_AGGREGATOR_URL = os.environ.get("LOG_AGGREGATOR_URL")
SERVICE_NAME = "article-ingest-service"

# --- 初期化 (Initialization) ---
try:
    firebase_admin.initialize_app()
    db = firestore.client()
except Exception as e:
    db = None
    print(f"CRITICAL in {SERVICE_NAME}: Failed to initialize Firestore. Error: {e}")

def report_error(error_message, context, tb_str):
    """中央エラーロガーにエラーを報告するヘルパー関数"""
    if not LOG_AGGREGATOR_URL:
        print(f"ERROR in {SERVICE_NAME}: LOG_AGGREGATOR_URL is not set. Cannot report error.")
        return
    try:
        log_payload = {
            "serviceName": SERVICE_NAME,
            "errorMessage": error_message,
            "context": context,
            "traceback": tb_str
        }
        requests.post(LOG_AGGREGATOR_URL, json=log_payload, timeout=5)
    except Exception as report_e:
        print(f"CRITICAL in {SERVICE_NAME}: Failed to send error report. Report Error: {report_e}")

@functions_framework.http
def article_ingest_service(request):
    """
    APIゲートウェイから転送されたJSONデータを受け取り、
    一次保管庫 (staging collections) にデータを保存する。
    """
    if not db:
        return jsonify({"status": "error", "message": "サーバーエラー: データベース接続不可"}), 500

    if request.method != 'POST':
        return jsonify({"status": "error", "message": "POSTメソッドを使用してください。"}), 405

    try:
        incoming_data = request.get_json()
        if not incoming_data:
            return jsonify({"status": "error", "message": "リクエストが無効です: JSONデータがありません。"}), 400

        if not incoming_data.get('title') or not incoming_data.get('sourceType'):
             return jsonify({"status": "error", "message": "必須フィールド(title, sourceType)が不足しています。"}), 400

        batch = db.batch()
        current_time = datetime.now(timezone.utc)

        # 1. Articleを一次保管庫に保存 (憲章3.3準拠)
        article_staging_ref = db.collection('staging_articles').document()
        article_doc_to_stage = {
            'title': incoming_data.get('title'),
            'sourceType': incoming_data.get('sourceType'),
            'description': incoming_data.get('description', ''),
            'keywords': incoming_data.get('keywords', []),
            'content': incoming_data,
            'aiGenerated': {},
            'status': 'received',
            'createdAt': current_time,
            'updatedAt': current_time
        }
        batch.set(article_staging_ref, article_doc_to_stage)

        # 2. Dictionaryの「種」を一次保管庫に保存 (憲章3.4準拠)
        keywords_for_dict = incoming_data.get('keywords', [])
        staged_keywords_count = 0
        if isinstance(keywords_for_dict, list):
            for keyword in keywords_for_dict:
                if not isinstance(keyword, str) or not keyword.strip():
                    continue
                dict_staging_ref = db.collection('staging_dictionary').document()
                dict_doc_to_stage = {
                    'termName': keyword,
                    'mentionedInArticleIds': [article_staging_ref.id],
                    'status': 'new_term_candidate',
                    'version': 1,
                    'createdAt': current_time,
                    'updatedAt': current_time
                }
                batch.set(dict_staging_ref, dict_doc_to_stage)
                staged_keywords_count += 1

        batch.commit()

        print(f"SUCCESS: Staged article {article_staging_ref.id} and {staged_keywords_count} dictionary terms.")

        return jsonify({
            "status": "success",
            "message": f"受領しました。記事と{staged_keywords_count}個の辞書候補を、司書たちに預けました。",
            "stagedArticleId": article_staging_ref.id
        }), 200

    except Exception as e:
        tb_str = traceback.format_exc()
        error_msg = str(e)
        report_error(error_msg, {"request_data": request.get_data(as_text=True)}, tb_str)
        return jsonify({"status": "error", "message": "情報の受付中にサーバー内部でエラーが発生しました。"}), 500
