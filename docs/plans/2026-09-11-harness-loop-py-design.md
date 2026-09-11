# harness-loop-py — design del repo

Stato: brief, da costruire. Stima: 6 giorni. Licenza: MIT. Target: Nearform Senior AI / Agentic Python (hiring manager probabile: Alfonso Graziano, AI Lead).

## Obiettivo

Reimplementare in Python il loop di harness engineering che Nearform descrive in pubblico (talk "Agents Building Agents", articolo AutoAgent: agente ottimizzatore che itera sulle eval, 18% → 83% in circa dieci iterazioni), dichiarandolo apertamente nel README, ed estenderlo con tre cose che la descrizione pubblica non ha:

1. **Budget di costo per iterazione.** Il loop si ferma quando il guadagno marginale per euro scende sotto soglia. Curva costo/pass-rate nel README.
2. **Gate di regressione per categoria.** Un'ipotesi che alza il pass rate totale ma abbassa una categoria di eval viene rifiutata.
3. **Feedback umano dentro il loop.** I casi segnalati da un endpoint di feedback entrano nel dataset con peso maggiore: l'iterazione successiva punta a ciò che gli utenti hanno bocciato.

Non è un porting del loro codice: il codice non è pubblico. È il loro metodo, sullo stack per cui assumono, con una misura in più.

## Architettura

```
agent_under_test/     LangGraph: router + 3 tool (sql su SQLite, lookup, calc)
evals/
  dataset.yaml        40 casi, ognuno con category, input, expected, check (exact|contains|judge)
  run.py              esegue il dataset, produce results.json con pass per caso e per categoria
  judge.py            LLM-as-a-judge per i casi a testo libero, rubrica a dimensioni pesate
optimizer/
  loop.py             ipotesi → branch git → modifica prompt/tool descriptions → eval → keep/rollback → changelog
  budget.py           costo per iterazione da Langfuse, regola di stop sul guadagno marginale
  gates.py            gate per categoria: rifiuta se una categoria peggiora
feedback/
  api.py              FastAPI POST /feedback {trace_id, verdict, note} → casi annotati
  ingest.py           trasforma i feedback in eval pesate (peso 2x) nel dataset
CHANGELOG.md          una riga per ipotesi: accettata/rifiutata, delta totale, delta per categoria, costo
```

Langfuse traccia ogni run dell'agente e ogni iterazione dell'optimizer, con costo. L'optimizer è pilotato da Claude Code (o da un nodo LangGraph con lo stesso prompt) e lavora su branch `hyp/<n>`.

## Cosa portare da n8n-docker (pattern, non codice)

Il codice EMS è di CP Sistemi: si riscrive da zero, su un dominio diverso, portando il disegno.

| Pattern in n8n-docker | Dove | Come rientra qui |
|---|---|---|
| Eval a tre livelli: contesto deterministico, giudice LLM a dimensioni pesate, composito con penalità anti-allucinazione | `scripts/eval_fetch.py`, `scripts/eval_push.py`, design 2026-04-09 | `evals/judge.py`: rubrica con pesi dichiarati (faithfulness, coherence, completeness) e penalità moltiplicativa se il giudice trova dati inventati. È il pezzo che rende le eval a testo libero difendibili |
| Span di contesto eval sulla traccia Langfuse (risposta finale, metadati, risultati) | `src/observability/eval_context.py` | Ogni run dell'agente logga un span `eval_context` con output strutturato: l'optimizer legge da lì, non dai log |
| Feedback utente con `trace_id` propagato nello state e nell'evento finale, e fetch "solo con feedback" | `src/api/feedback.py`, `eval_fetch --with-feedback-only` | Estensione 3: stesso schema, il feedback diventa eval pesata |
| Benchmark con casi tipizzati e analisi deterministica dell'output (le TRAP) prima del giudice | `tests/benchmark/sql_agent_benchmark.py` | `evals/run.py`: check deterministici prima, giudice dopo. Categorie del dataset = classi di errore, come le TRAP |
| Errori classificati in macro-categorie con retriable sì/no e `MAX_RETRIES=1` | `sql_agent_v2.py` | L'agente sotto test ha lo stesso schema di errore: dà all'optimizer un segnale pulito su cosa migliorare |
| Benchmark YAML con target dichiarato e la motivazione scritta del perché quel target | `tests/benchmark/rag_benchmark_queries.yaml` | `evals/dataset.yaml` con `target` e commento: il README spiega il tetto strutturale, non solo il numero |
| Registrazione Langfuse automatica in `get_llm()`, silente se mancano le chiavi | `src/utils/llm.py` | Stessa scelta: il repo gira senza Langfuse, con Langfuse mostra i costi |

Cosa non portare: il catalogo TRAP, il domain model, i prompt EMS. Sono dominio del cliente.

## Piano in 6 giorni

| Giorno | Consegna |
|---|---|
| 1 | Agente sotto test + dataset 40 casi in 4 categorie + `evals/run.py` con report per categoria |
| 2 | Giudice LLM con rubrica pesata e penalità; Langfuse con costi; span `eval_context` |
| 3 | Optimizer loop: ipotesi, branch, eval, keep/rollback, changelog. Prima curva pass-rate per iterazione |
| 4 | Budget di costo e regola di stop; gate per categoria; test che dimostra un rollback per regressione di categoria |
| 5 | Feedback endpoint + ingest pesato; run che recupera un caso segnalato |
| 6 | README con tabelle e curve, seed fisso, comando unico di riproduzione, crediti al talk, licenza MIT |

## Cosa deve mostrare il README

- Tabella pass rate per iterazione, totale e per categoria.
- Curva costo cumulato vs pass rate, con il punto in cui la regola di stop scatta.
- Conteggio delle ipotesi rifiutate dal gate per categoria, con un esempio concreto.
- Iterazioni necessarie a recuperare un caso arrivato dal feedback.
- Un comando che riproduce esattamente gli stessi numeri.
- Sezione "Origine": link al talk e all'articolo, cosa è preso dal metodo pubblico, cosa è aggiunto.

## Non-obiettivi

UI, multi-repo, sandbox VM, astrazione multi-provider oltre Anthropic/OpenRouter, ottimizzazione del codice dei tool (solo prompt e descrizioni).

## Rischi

- **Percezione di copia.** Mitigata dalla trasparenza nel README e dalle tre estensioni misurabili. Mai chiamarlo "AutoAgent".
- **Numeri poco impressionanti.** Un agente minimo che parte basso è voluto: il messaggio è la curva, non il valore finale.
- **Costo API.** 40 casi per iterazione per 10 iterazioni: tenere il modello piccolo per l'agente sotto test, il modello grande solo per l'optimizer.
