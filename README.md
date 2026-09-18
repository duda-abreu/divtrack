# DivTrack

API FastAPI para registrar e acompanhar dividendos.

## Executar

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn main:app --reload
```

Documentação: `http://127.0.0.1:8000/docs`.

Banco SQLite criado em `divtrack.db`. Use `DIVTRACK_DB_PATH` para alterar o caminho.

## Endpoints

- `GET /` — health check
- `POST /dividends` — cadastra dividendo
- `GET /dividends` — lista e filtra por ticker/período
- `GET /dividends/summary` — totaliza por moeda
- `GET /dividends/{id}` — consulta registro
- `PATCH /dividends/{id}` — atualiza registro
- `DELETE /dividends/{id}` — remove registro

## Testes

```powershell
pytest -q
```
