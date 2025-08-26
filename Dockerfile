# ==============================================================================
# Dockerfile for Article Ingest Service (Corrected)
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

# 1. 先に依存関係をコピー (この時点ではrootユーザー)
COPY requirements.txt .

# 2. システムへのインストールはroot権限で実行
RUN pip install --no-cache-dir -r requirements.txt

# 3. アプリケーション実行用の非rootユーザーを作成
RUN adduser --system --group appuser

# 4. アプリケーションコードをコピーし、所有者をappuserに変更
COPY --chown=appuser:appuser . .

# 5. インストール完了後、非rootユーザーに切り替え
USER appuser

# Cloud RunのPORT環境変数を設定
ENV PORT 8080

# 6. アプリケーションは非rootユーザーで実行される
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "main:app"]
