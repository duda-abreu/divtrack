# DivTrack

API FastAPI para registrar e acompanhar dividendos.

## Executar

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn main:app --reload
```

Interface: `http://127.0.0.1:8000/`.

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
- `POST /portfolios` — cria carteira
- `GET /portfolios` — lista carteiras
- `GET /portfolios/{id}` — consulta carteira
- `PATCH /portfolios/{id}` — atualiza carteira
- `DELETE /portfolios/{id}` — remove carteira sem apagar dividendos
- `POST /holdings` — cadastra ou atualiza ação possuída
- `GET /holdings` — lista ações da carteira
- `PATCH /holdings/{id}` — atualiza posição
- `DELETE /holdings/{id}` — remove posição
- `POST /sync/dividends` — busca novos proventos das ações cadastradas

Dividendos aceitam `portfolio_id`. Listagem e resumo também filtram por carteira.

## Sincronização automática

Dados de ações e proventos vêm da [brapi.dev](https://brapi.dev/). PETR4, VALE3,
MGLU3 e ITUB4 funcionam no sandbox. Para outros tickers, configure:

```powershell
$env:BRAPI_TOKEN="seu-token"
```

A API sincroniza ao iniciar e a cada 6 horas. Altere o intervalo em segundos com
`DIVTRACK_SYNC_INTERVAL` (mínimo: 300). A interface também possui botão
**Sincronizar**.

## Testes

```powershell
pytest -q
```
