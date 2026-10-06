$env:AI_DND_CAMPAIGN_DB = 'C:\Users\Kadir\Desktop\AI-DND-pre04-wave3\ai-dnd\reports\wave3-local-live-20261006\campaigns-temp-fix.sqlite3'
$env:OLLAMA_HOST = 'http://127.0.0.1:8787'
Set-Location 'C:\Users\Kadir\Desktop\AI-DND-pre04-wave3\ai-dnd'
python -m uvicorn api.main:app --host 127.0.0.1 --port 8008
