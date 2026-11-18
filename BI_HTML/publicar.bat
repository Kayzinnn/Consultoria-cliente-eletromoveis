@echo off
REM Publica o BI em HTML no Cloudflare Pages (o login fica a cargo do Cloudflare Access).
REM Uso: dois cliques neste arquivo, ou no terminal: BI_HTML\publicar.bat
setlocal
set PROJETO=painel-zemaria

cd /d "%~dp0\.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

echo.
echo [1/2] Exportando os dados do banco...
python BI_HTML\exportar_dados.py
if errorlevel 1 goto erro

echo.
echo [2/2] Enviando para o Cloudflare Pages (%PROJETO%)...
call npx --yes wrangler pages deploy BI_HTML\site --project-name %PROJETO% --branch main --commit-dirty=true
if errorlevel 1 goto erro

echo.
echo Publicado. Confira em https://%PROJETO%.pages.dev (pede o codigo do e-mail).
pause
exit /b 0

:erro
echo.
echo Algo deu errado. Leia a mensagem acima.
pause
exit /b 1
