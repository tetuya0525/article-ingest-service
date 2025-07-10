# Python 3.12の公式イメージをベースとして使用
FROM python:3.12-slim

# コンテナ内の作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー
COPY requirements.txt .

# 依存関係をインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY main.py .

# コンテナがリッスンするポートを8080に設定
ENV PORT=8080

# gunicornを使って、main.py内のFlaskアプリ「app」を起動
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
