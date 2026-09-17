# PRD — harness-loop-py

Versione 0.3, 2026-09-16, aggiornata 2026-09-17. Stato: sei giorni consegnati; quattro loop, 13 ipotesi, un caso da feedback recuperato in 2 iterazioni, varianza su 3 run nel README. Decisioni dei giorni 2-6 in §12 (D4 emendata due volte con l'evidenza dei loop). Versioni precedenti: 0.2 del 2026-09-16, 0.1 del 2026-09-11.

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

## 12. Decisioni del grill, giorni 2-6 (2026-09-16, secondo grill)

Quindici domande sulla frontiera dei giorni 2-6, chiuse in un giro. §11 non è stato riaperto.

| # | Domanda | Decisione | Perché |
|---|---|---|---|
| D1 | `evals/results/runs.jsonl` | Una riga per run dell'agente, append-only, **ignorata da git**: `trace_id, ts, case_id, category, check, expected/reference, input, answer, refused, error, tool_calls (output troncato a 1500), passed, detail, cost_usd, model, git_sha, results_file, iteration` | Il results file è l'evidenza; il log locale serve solo a ricostruire un caso dal `trace_id` per il feedback. Le righe usate nel demo finiscono in `evals/feedback.yaml` |
| D2 | Trace e span Langfuse | Una trace per caso, `trace_id` generato localmente e deterministico da `ts:case_id` (lo stesso di `runs.jsonl`, funziona senza chiavi). Span `eval_context` con input `{case_id, category, check, expected}`, output `{answer, refused, error, passed, detail, score}`, metadata `{seed, git_sha, results_file, iteration, hypothesis_id, cost_usd, model}`, tag `[category, split, passed\|failed]`. Il giudice è una generation figlia della stessa trace | Costo per caso in Langfuse = agente + giudice, confrontabile col results file. Il confronto è manuale: una riga nel README quando esistono le chiavi |
| D3 | Formato dell'ipotesi | Output strutturato `{title, rationale, target: system.md\|tools.yaml, content, proposed_cases}` con il **file intero**; un target per iterazione; cap 6000 char per `system.md`, 3000 per `tools.yaml`; `tools.yaml` deve conservare le 4 chiavi. Cap superato → `rejected: too_long`, senza eval | I diff prodotti da un LLM sbagliano gli spazi; il file intero è robusto e git mostra il diff |
| D4 | Cosa vede l'ottimizzatore | Fallimenti `visible` con `expected`/`reference`, pass rate visible per categoria, i due file di prompt, ultime righe del changelog. Mai holdout. Difese contro le risposte cablate: regola nel prompt, holdout nel gate, check deterministico `rejected: leaks_expected` se `content` contiene un `expected` letterale **di un caso visible fallito** (emendato 2026-09-17: il check sui casi che già passano ha bloccato cinque ipotesi su "Switzerland" dentro una lista di codici ISO; l'ottimizzatore vede `expected` solo dei falliti, il check copre esattamente ciò che vede) | Un umano vedrebbe la risposta attesa; la difesa è strutturale, non l'ignoranza |
| D5 | L'ottimizzatore legge il codice | Sì, in sola lettura: `ledger.py`, `tools.py`, `graph.py`. Modifica solo i due file di prompt | Mettere lo schema nel prompt è il miglioramento legittimo che il metodo pubblico fa leggendo il codebase |
| D6 | Branch e main | Working tree sporco → il loop non parte. `hyp/<n>` da `main`, commit dell'ipotesi, eval nel branch. Accettata → fast-forward di `main` (commit dell'ipotesi) più un commit di evidenza (results, changelog, loop file, proposed). Rifiutata → solo il commit di evidenza. I branch rifiutati restano. Il loop parte con un'iterazione 0: eval di `main` committata come punto di partenza della curva | Lo sha nel results file deve puntare al commit dell'ipotesi che lo ha prodotto, quindi l'evidenza arriva in un commit successivo; la curva costo non ha buchi |
| D7 | Riga di `CHANGELOG.md` | `\| n \| hyp \| sha \| target \| title \| verdict \| visible Δ \| lookup/aggr/reas/ref Δ (casi) \| holdout Δ \| cost € \| cumul € \| results \|`; verdict ∈ `accepted`, `rejected: no_gain`, `rejected: gate <cat> -k`, `rejected: holdout`, `rejected: too_long`, `rejected: leaks_expected`; riga finale `stop: budget\|max_iterations\|max_eur` | Delta per categoria in casi, leggibili con 7-8 casi visible per categoria |
| D8 | `src/optimizer/prompt.md` | Generico: ruolo, vincoli D3-D4, euristiche di metodo (una causa, una modifica, la più piccola che spiega più fallimenti), formato input e output. Zero conoscenza del dominio | Se il prompt dice cosa non funziona, la curva è mia e non dell'ottimizzatore |
| D9 | Budget | `BUDGET_MIN_GAIN_PER_EUR=0.03` (punti di pass rate visible per euro), finestra 3, nel costo entrano iterazioni rifiutate e chiamate dell'ottimizzatore. `MAX_ITERATIONS=12`, `MAX_TOTAL_EUR=10` | Con 0.01 lo stop non scatterebbe mai in 12 iterazioni e O2 non si dimostra |
| D10 | File di riepilogo del loop | `evals/results/loops/<ts>.json` con parametri, tolleranze per categoria, una voce per iterazione, `stop {reason, at}`, `feedback {...}` | Unica fonte per grafici e tabelle del README |
| D11 | Cosa diventa un feedback | Run di un caso del dataset → `feedback.yaml` `{id, ref, verdict, note, trace_id, ts}` e `load_cases` ripesa il caso a `FEEDBACK_WEIGHT`. Run ad hoc → nuovo caso `judge` con `reference: note`, `category` obbligatoria nel body. `good` registrato, pesi invariati | Niente duplicati dello stesso input; la via ad hoc esiste ma il demo usa la prima |
| D12 | Iterazioni per recuperare | Il loop rilegge `feedback.yaml` a ogni iterazione. Nel loop file `feedback: {FB01: {ref, flagged_before_iteration: k, recovered_at_iteration: j}}`; recuperato = primo `j ≥ k` in cui il caso passa in un'iterazione **accettata**; N = j − k + 1 | Nessun resume da implementare: il feedback arriva via HTTP mentre il loop gira |
| D13 | Varianza | 3 run completi del prompt finale: min/mean/max su totale e categorie, più il numero di casi che cambiano esito. Baseline solo se avanza budget | Il prompt finale è il numero che qualcuno prova a riprodurre |
| D14 | Grafici | `scripts/plot.py`, matplotlib nel gruppo dev, `docs/img/*.svg` dal loop file | Cento righe di SVG a mano sono più manutenzione di una dipendenza noiosa |
| D16 | Conferma holdout (2026-09-17, dopo la varianza) | Un'ipotesi che supera il gate viene rieseguita sui soli 10 casi holdout; accettata solo se anche il secondo run non scende; l'holdout di riferimento diventa il minimo dei due. Spec `docs/plans/2026-09-17-holdout-confirmation.md` | L'ipotesi 12 era passata per un'estrazione fortunata di `F08`: tre run successivi la smentiscono. Due run su due è la regola più semplice che l'avrebbe fermata |
| D15 | Origin | Testo attuale più URL del talk e dell'articolo, data di consultazione, e "the 18% → 83% figure is theirs, not reproduced here" | I loro numeri non sono i nostri |

Nota sul giorno 2: la baseline porta lo sha `28e0ffb`, precedente al commit del codice. Da qui in poi l'ordine è: commit del codice, `just evals`, commit del results file, così lo sha nel file punta al codice che lo ha prodotto.
