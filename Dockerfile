FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-next.txt ./
RUN pip install --no-cache-dir -r requirements-next.txt
COPY evidex_hosted.py evidex_hosted.js evidex_next.py evidex_next.html evidex_next.css evidex_next_content.json evidence_excel.py evidence_store.py telegram_connection.py ./
COPY guide_assets/ ./guide_assets/
COPY agency_assets/ ./agency_assets/
CMD ["python", "evidex_hosted.py"]
