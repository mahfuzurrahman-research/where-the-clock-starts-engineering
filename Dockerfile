FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN chmod +x run_public_demo.sh
CMD ["./run_public_demo.sh"]
