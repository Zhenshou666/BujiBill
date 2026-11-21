# 不记账本 · 服务端镜像
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8

WORKDIR /app

# 先装依赖，代码改动时可以复用这层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY billkit ./billkit
COPY ui ./ui
COPY data/rules.json ./data/rules.json
COPY tools/campus_grab.js ./tools/campus_grab.js

# 1 = 分享模式：每个访客各一份空账本，看不到宿主数据
ENV BILLKIT_SHARE=1

EXPOSE 8501

# 健康检查用 python 而不是 curl：slim 镜像里没有 curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status==200 else 1)"

CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--browser.gatherUsageStats", "false", \
     "--server.enableCORS", "false", \
     "--server.enableXsrfProtection", "false", \
     "--server.enableWebsocketCompression", "false"]
