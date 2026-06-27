FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
# CPU-only torch avoids ~500MB CUDA wheels and keeps sentence-transformers installable in slim images.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
ENV HF_HUB_DISABLE_TELEMETRY=1
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
