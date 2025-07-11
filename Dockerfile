# ベースイメージとして公式のPython 3.12スリム版を使用
# Use the official Python 3.12 slim image as a base
FROM python:3.12-slim

# 作業ディレクトリを設定
# Set the working directory
WORKDIR /app

# アプリケーションのソースコードと要件ファイルをコピー
# Copy the application source code and requirements file
COPY main.py .
COPY requirements.txt .

# 環境変数 PORT を設定 (Cloud Runの要件)
# Set the PORT environment variable (required by Cloud Run)
ENV PORT 8080

# Pythonのパッケージインストーラーpipをアップグレードし、要件ファイルをインストール
# Upgrade pip and install the requirements
RUN pip install --no-cache-dir --upgrade pip -r requirements.txt

# コンテナ起動時に実行するコマンドを設定
# Set the command to run when the container starts
# functions-frameworkがHTTPリクエストを待ち受け、main.pyのhttp_entryポイントを呼び出す
# functions-framework will listen for HTTP requests and call the http_entry point in main.py
CMD ["functions-framework", "--target=http_entry", "--source=main.py"]
