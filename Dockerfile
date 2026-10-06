FROM python:3.11-slim
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY google_ads_api_server.py .
COPY growider_all_campaigns.json .
EXPOSE 8000
CMD ["python3", "google_ads_api_server.py"]
