FROM node:22-bookworm-slim AS camera
WORKDIR /camera
COPY games/camera/package*.json ./
RUN npm ci
COPY games/camera/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY games/__init__.py games/state.py games/service.py /app/games/
COPY games/display /app/games/display
COPY games/receiver /app/games/receiver
COPY --from=camera /camera/dist /app/games/camera/dist
USER 10001:10001
EXPOSE 8766
HEALTHCHECK --interval=30s --timeout=5s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8766/health',timeout=3).read()"]
ENTRYPOINT ["python", "-m", "games.service"]
CMD ["serve", "--config", "/run/terebi.json"]
