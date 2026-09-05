FROM python:3.12-alpine
WORKDIR /app
COPY app.py /app/app.py
COPY static /app/static
RUN addgroup -S fleet && adduser -S -G fleet fleet
USER fleet
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 CMD wget -q -O- http://127.0.0.1:8080/healthz >/dev/null || exit 1
CMD ["python", "/app/app.py"]
