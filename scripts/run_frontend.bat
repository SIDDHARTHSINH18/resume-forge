@echo off
rem Start the Vite dev server on http://127.0.0.1:5421 (proxies /api to 127.0.0.1:8421).
cd /d "%~dp0..\frontend"
npm run dev
