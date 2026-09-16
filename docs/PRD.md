# PRD — harness-loop-py

Versione 0.2, 2026-09-16. Stato: decisioni del grill chiuse (§11), giorno 1 in corso. Versione precedente: 0.1 del 2026-09-11.

## 1. Problema

Chi costruisce agenti LLM migliora i prompt a mano: cambia una frase, rilancia tre esempi, decide a occhio. Il metodo che Nearform descrive in pubblico (un agente ottimizzatore che itera sulle eval, tiene ciò che migliora e fa rollback del resto) risolve questo, ma esiste solo come talk, articolo e IP proprietaria in TypeScript. Non esiste una versione Python di riferimento, e la descrizione pubblica ignora tre cose che in produzione contano: quanto costa ogni miglioramento, se un miglioramento globale nasconde una regressione locale, e come il feedback degli utenti entra nel ciclo.

## 2. Perché esiste questo repo

Due destinatari, in quest'ordine.

1. **Hiring manager AI (Nearform, Finom, Duferco, altri).** Deve leggere il README in due minuti e concludere: capisce il metodo, sa portarlo in Python, ha aggiunto misure che il metodo pubblico non ha.
2. **Me, tra sei mesi.** Deve essere il loop che uso davvero per migliorare un agente, non una demo.

Se le due cose entrano in conflitto, vince la prima fino alla candidatura, la seconda dopo.

## 3. Obiettivi

| # | Obiettivo | Misura di successo |
|---|---|---|
| O1 | Il loop porta un agente minimo da un pass rate basso a uno alto senza intervento umano | Curva pass rate per iterazione nel README, rilanciabile con un comando |
| O2 | Ogni miglioramento ha un prezzo visibile | Curva costo cumulato vs pass rate; punto di stop del budget segnato |
| O3 | Nessuna regressione nascosta | Almeno un'ipotesi rifiutata dal gate per categoria, documentata nel changelog |
| O4 | Il feedback umano cambia la direzione del loop | Un caso segnalato via endpoint viene recuperato entro N iterazioni, con N nel README |
| O5 | Trasparenza sull'origine | Sezione Origin con link al talk e all'articolo; nessuna riga di codice di terzi |

## 4. Non-obiettivi

- Ottimizzare il codice dei tool: il loop tocca solo prompt e descrizioni dei tool.
- UI, dashboard, multi-repo, sandbox VM.
- Astrazione multi-provider: un solo client OpenAI-compatible con `LLM_BASE_URL` configurabile. Default Anthropic; chi clona mette OpenRouter o altro.
- Battere i numeri di Nearform. Il messaggio è la curva e le tre estensioni, non il valore finale.
- Generalità: un solo agente sotto test, un solo dataset, un solo dominio.

## 5. Utenti e scenari

- **Il lettore del README** apre la tabella, vede tre curve, legge Origin, clona e lancia `just evals` con la propria chiave: ottiene numeri compatibili con la varianza dichiarata.
- **Io che sviluppo** scrivo un caso nel dataset, lancio il loop, leggo il changelog e decido se accettare l'ipotesi del loop o annotarla come feedback.
- **Un utente dell'agente** (simulato) boccia una risposta via `POST /feedback`; alla prossima iterazione quel caso pesa doppio.

## 6. Requisiti funzionali

### Agente sotto test
- R1. Dominio: **registro contabile di una PMI** su SQLite, tre tabelle (`customers`, `invoices`, `payments`), dati fissi scritti a mano nel codice, data di riferimento fissa `2026-09-01`. Grafo LangGraph con un nodo LLM, un nodo tool e tre tool: `run_sql` (sola lettura), `lookup_customer`, `compute`. La risposta finale è un quarto tool, `final_answer(answer, refused)`: l'output strutturato è un tool call, non un parsing di testo.
- R2. Prompt di sistema e descrizioni dei tool vivono in `src/agent_under_test/prompts/` (`system.md`, `tools.yaml`): sono l'unica superficie che l'ottimizzatore può modificare. Il prompt di partenza è minimo di proposito, non sabotato.
- R3. Ogni run produce `AgentResult` (Pydantic): risposta, `refused`, errore esplicito (`no_final_answer`, `max_steps`, `provider_error`), tool call eseguiti con output, token e costo. Mai un numero senza esecuzione del tool.

### Eval
- R4. Dataset YAML: `id`, `category`, `input`, `expected`, `check`, `weight` (default 1), `source` (`seed` | `feedback`), `split` (`visible` | `holdout`). Check disponibili: `exact`, `contains` (tutte le sottostringhe), `contains_any`, `number` (tolleranza 0.5% o 0.01), `refused` (il campo strutturato), `judge`.
- R5. Quattro categorie, 10 casi ciascuna: `lookup`, `aggregation`, `reasoning`, `refusal`. `refusal` copre scritture, richieste fuori dai dati, previsioni, decisioni di credito e prompt injection: l'agente deve rifiutare, non inventare.
- R6. Check deterministici prima; giudice LLM solo per `judge`, con risposta di riferimento nel dataset, rubrica a dimensioni pesate (correttezza 0.5, ancoraggio ai tool 0.3, completezza 0.2) e penalità moltiplicativa 0.3 se il giudice trova un numero senza evidenza nei tool output. Soglia di pass 0.7. Giudice a temperatura 0.
- R7. Risultati in `evals/results/<ts>.json` con: modelli, seed, sha, costo (agente e giudice separati), pass per caso, pass rate per categoria, per split (visibile e holdout) e totale pesato.
- R8. Nessun caso può essere indebolito per far passare un run: si aggiunge, non si cambia. Il diff del dataset è parte della review. Il dataset di valutazione lo modifica solo un umano.

### Ottimizzatore
- R9. Ciclo: leggi ultimi risultati e fallimenti per categoria sui soli casi `visible` → proponi una ipotesi (una sola modifica) → branch `hyp/<n>` → applica → eval → confronta.
- R10. Gate: accetta solo se il pass rate totale sui casi visibili sale, nessuna categoria scende di più di **un caso** (`tolerance = 1/n_categoria`, calcolata dal dataset, non cablata) e il pass rate sull'holdout non scende. Altrimenti rollback del branch.
- R11. Ogni iterazione scrive una riga nel `CHANGELOG.md`: ipotesi, esito, delta totale, delta per categoria, costo in euro.
- R12. Budget: costo per iterazione calcolato localmente dai token (`usage_metadata`) con una tabella prezzi versionata in `src/pricing.py`; Langfuse serve alle tracce, non al costo. Stop quando il guadagno marginale per euro sulle ultime 3 iterazioni scende sotto `BUDGET_MIN_GAIN_PER_EUR`.
- R13. Tetto duro: `MAX_ITERATIONS` e `MAX_TOTAL_EUR`, entrambi in `.env`, entrambi nel results file.
- R14. Il pilota del loop è un **nodo LangGraph programmatico** con prompt versionato in `src/optimizer/prompt.md` e modello pinnato. Claude Code è lo strumento di sviluppo del repo, non il pilota: un loop guidato da una sessione interattiva non è rilanciabile dal lettore.
- R19. L'ottimizzatore può **proporre** casi in `evals/proposed.yaml`; entrano nel dataset solo se un umano li sposta a mano. R8 resta vero.

### Feedback
- R15. `POST /feedback {trace_id, verdict, note}`; il caso viene ricostruito dal log locale dei run (`evals/results/runs.jsonl`), annotato e scritto in `evals/feedback.yaml` con `source: feedback` e peso `FEEDBACK_WEIGHT` (default 2, valore dichiaratamente arbitrario: "un umano lo ha guardato"). Revocare un feedback sbagliato è cancellare la riga: git lo traccia.
- R16. Il README riporta quante iterazioni servono a recuperare un caso segnalato (metrica O4).

### Osservabilità e riproducibilità
- R17. Langfuse opzionale, progetto dedicato `harness-loop-py`: senza chiavi tutto gira. Con chiavi: una traccia per run dell'agente, una per iterazione dell'ottimizzatore.
- R18. `just evals --seed 42` a temperatura 0. L'endpoint Anthropic ignora `seed`: il README lo dichiara e riporta la varianza su 3 run. Il seed resta nel results file e viene passato al provider per chi ne supporta uno.

## 7. Requisiti non funzionali

- Modelli: agente sotto test `claude-haiku-4-5-20251001` ($1/$5 per Mtok), giudice e ottimizzatore `claude-sonnet-4-6` ($3/$15). Un'iterazione completa su 40 casi deve costare meno di 1 euro.
- Client unico `ChatOpenAI` con `LLM_BASE_URL` + `LLM_API_KEY`; tool calling verificato sull'endpoint Anthropic il 2026-09-16.
- Il repo si installa con `uv sync` e i test unitari passano senza chiavi.
- Nessun dato personale, nessun dato di clienti, nessun codice di datori di lavoro. Il registro è inventato.
- README in inglese.

## 8. Metriche nel README (tutte da `evals/results/`)

1. Pass rate per iterazione, totale, per categoria, visibile e holdout.
2. Costo cumulato e guadagno marginale per euro; iterazione in cui scatta lo stop.
3. Ipotesi rifiutate dal gate per categoria, con un esempio.
4. Iterazioni per recuperare un caso da feedback.
5. Varianza su 3 run a temperatura 0.

## 9. Milestone

| Giorno | Consegna | Criterio di done |
|---|---|---|
| 1 | Registro SQLite + agente + dataset 40 casi + giudice + `evals/run.py` | Un results file reale, pass rate baseline nel README |
| 2 | Langfuse (progetto dedicato) + span `eval_context` + `runs.jsonl` | Tracce visibili; costo per run nel results file confrontato con Langfuse |
| 3 | Nodo ottimizzatore con branch, keep/rollback, changelog | Prima curva pass rate per iterazione |
| 4 | Budget e gate per categoria + holdout | Uno stop per budget e un rifiuto per regressione documentati |
| 5 | Feedback endpoint e ingest pesato | Un caso segnalato recuperato |
| 6 | README finale, Origin, riproducibilità | Tre run, varianza riportata |

## 10. Rischi e decisioni prese

| Rischio | Decisione |
|---|---|
| Letto come copia di Nearform | Origin esplicito (§11 Q8), nome diverso, tre estensioni misurabili in README |
| Loop che "impara" il dataset (overfitting ai 40 casi) | Split: 30 casi `visible` all'ottimizzatore, 10 `holdout` riportati a parte e nel gate. Il README mostra entrambi |
| Giudice LLM che premia risposte lunghe | Rubrica con penalità e casi `refusal` che premiano il rifiuto corretto |
| Ottimizzatore che compiace il giudice (stesso modello) | Tre categorie su quattro sono deterministiche e non si possono compiacere; giudice a temperatura 0 con riferimento; rischio dichiarato nel README |
| Costi API fuori controllo | R13, tetti duri in `.env` |
| Non determinismo del provider | R18, varianza dichiarata |

## 11. Decisioni del grill (2026-09-16)

Le sette domande aperte della v0.1 e le assunzioni implicite, chiuse in due giri.

| # | Domanda | Decisione | Perché |
|---|---|---|---|
| Q1 | Dominio dell'agente | Registro PMI: clienti, fatture, pagamenti | Deterministico come ordini/clienti, ma parla a fintech ed energia; i rifiuti ("quante tasse pagheremo") vengono naturali |
| Q2 | Provider e modelli | Un client OpenAI-compatible, default Anthropic; Haiku 4.5 agente, Sonnet 4.6 giudice e ottimizzatore | Zero codice in più, chi clona sceglie il provider; il modello piccolo tiene l'iterazione sotto 1 euro |
| Q3 | Pilota del loop | Nodo LangGraph dal giorno 3; Claude Code solo per sviluppare | Il lettore deve poter rilanciare la curva |
| Q4 | Giudice = ottimizzatore? | Stesso modello, giudice a temperatura 0, 3 categorie su 4 deterministiche | Un secondo provider è un non-obiettivo; la difesa è strutturale |
| Q5 | Tolleranza del gate | Un caso per categoria, calcolata da `n`; holdout non deve scendere | Con 10 casi la tolleranza zero rifiuta quasi tutto; con 30 casi scende da sola |
| Q6 | L'ottimizzatore aggiunge casi? | Solo proposte in `evals/proposed.yaml`, accettazione umana | Un loop che scrive i propri esami è autoreferenziale |
| Q7 | Peso e revoca del feedback | `FEEDBACK_WEIGHT` default 2, casi in `evals/feedback.yaml`, revoca = cancellare la riga | Il 2 è arbitrario e lo si dice; git traccia la revoca |
| Q8 | Confine dell'Origin | Dal metodo pubblico: ottimizzatore su eval con keep/rollback, 18%→83%. Conoscenza generale: eval-driven development, LLM-as-judge, branch per ipotesi. Aggiunto qui: budget marginale, gate per categoria, feedback pesato. "Nearform non ha pubblicato codice; questa è una reimplementazione indipendente del metodo descritto." | Chiude ogni discussione di copia |
| Q9 | Progetto Langfuse | Progetto dedicato, chiavi da creare; fino ad allora si gira senza | Le tracce di un repo pubblico non si mescolano con quelle di un cliente |
| Q10 | Costo per iterazione | Dai token con tabella prezzi locale, non da Langfuse | Il budget deve funzionare anche senza Langfuse (R17) |
| Q11 | Output strutturato | `final_answer` come tool call | L'endpoint compat ignora `response_format`; un tool call è deterministico da leggere |
| Q12 | Check numerici | Tipo `number` con tolleranza 0.5% | "24,890.00" e "24890" sono la stessa risposta; `contains` li tratterebbe diversamente |
| Q13 | Riferimento per il giudice | Ogni caso `judge` ha `reference` scritta a mano dai dati | Un giudice senza riferimento misura la plausibilità, non la correttezza |
| Q14 | Feedback senza autenticazione | Endpoint locale, nessuna auth, dichiarato nel README | È uno strumento di sviluppo, non un servizio esposto |
