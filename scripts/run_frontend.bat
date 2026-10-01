@echo off
rem Start the Vite dev server on http://localhost:5273 (proxies /api to 127.0.0.1:8100).
cd /d "%~dp0..\frontend"
npm run dev
