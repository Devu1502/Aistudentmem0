# ---------- Base Image ----------
FROM python:3.12-slim

# ---------- Working Directory ----------
WORKDIR /app

# ---------- Copy Project ----------
COPY . .

# ---------- Install Dependencies ----------
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Expose Port ----------
EXPOSE 8080

# ---------- Run FastAPI ----------
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
