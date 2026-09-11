# PRD — harness-loop-py

Versione 0.1, 2026-09-11. Stato: bozza da mettere sotto interrogatorio (grill-me) prima del giorno 1.

## 1. Problema

Chi costruisce agenti LLM migliora i prompt a mano: cambia una frase, rilancia tre esempi, decide a occhio. Il metodo che Nearform descrive in pubblico (un agente ottimizzatore che itera sulle eval, tiene ciò che migliora e fa rollback del resto) risolve questo, ma esiste solo come talk, articolo e IP proprietaria in TypeScript. Non esiste una versione Python di riferimento, e la descrizione pubblica ignora tre cose che in produzione contano: quanto costa ogni miglioramento, se un miglioramento globale nasconde una regressione locale, e come il feedback degli utenti entra nel ciclo.

## 2. Perché esiste questo repo

Due destinatari, in quest'ordine.

1. **Hiring manager AI (Nearform, poi altri).** Deve leggere il README in due minuti e concludere: capisce il nostro metodo, sa portarlo in Python, ha aggiunto una misura che noi non pubblichiamo.
2. **Me, tra sei mesi.** Deve essere il loop che uso davvero per migliorare un agente, non una demo.

Se le due cose entrano in conflitto, vince la prima fino alla candidatura, la seconda dopo.

## 3. Obiettivi

| # | Obiettivo | Misura di successo |
|---|---|---|
| O1 | Il loop porta un agente minimo da un pass rate basso a uno alto senza intervento umano | Curva pass rate per iterazione nel README, riproducibile con seed fisso |
| O2 | Ogni miglioramento ha un prezzo visibile | Curva costo cumulato vs pass rate; punto di stop del budget segnato |
| O3 | Nessuna regressione nascosta | Almeno un'ipotesi rifiutata dal gate per categoria, documentata nel changelog |
| O4 | Il feedback umano cambia la direzione del loop | Un caso segnalato via endpoint viene recuperato entro N iterazioni, con N nel README |
| O5 | Trasparenza sull'origine | Sezione Origin con link al talk e all'articolo; nessuna riga di codice di terzi |

## 4. Non-obiettivi

- Ottimizzare il codice dei tool: il loop tocca solo prompt e descrizioni dei tool.
- UI, dashboard, multi-repo, sandbox VM, multi-provider oltre Anthropic e OpenRouter.
- Battere i numeri di Nearform. Il messaggio è la curva e le tre estensioni, non il valore finale.
- Generalità: un solo agente sotto test, un solo dataset, un solo dominio (ordini e clienti su SQLite).

## 5. Utenti e scenari

- **Il lettore del README** apre la tabella, vede tre curve, legge Origin, clona e lancia `just evals` con la propria chiave: ottiene gli stessi numeri.
- **Io che sviluppo** scrivo un caso nel dataset, lancio il loop, leggo il changelog e decido se accettare l'ipotesi del loop o annotarla come feedback.
- **Un utente dell'agente** (simulato) boccia una risposta via `POST /feedback`; alla prossima iterazione quel caso pesa doppio.

## 6. Requisiti funzionali

### Agente sotto test
- R1. Grafo LangGraph con router e tre tool su SQLite: `run_sql`, `lookup_customer`, `compute`. Piccolo per scelta.
- R2. Prompt di sistema e descrizioni dei tool vivono in file di testo versionati: sono l'unica superficie che l'ottimizzatore può modificare.
- R3. Ogni run produce output strutturato (Pydantic) e un errore esplicito quando fallisce; mai un numero senza esecuzione del tool.

### Eval
- R4. Dataset YAML: id, categoria, input, atteso, tipo di check (`exact`, `contains`, `judge`), peso (default 1), origine (`seed` o `feedback`).
- R5. Quattro categorie fisse alla partenza: `lookup`, `aggregation`, `reasoning`, `refusal` (domande a cui l'agente deve dire di non poter rispondere).
- R6. Check deterministici prima; giudice LLM solo per `judge`, con rubrica a dimensioni pesate e penalità moltiplicativa se il giudice trova un numero senza evidenza.
- R7. Risultati in `evals/results/<ts>.json` con: modello, seed, sha, costo, pass per caso, pass rate per categoria e totale pesato.
- R8. Nessun caso può essere indebolito per far passare un run: si aggiunge, non si cambia. Il diff del dataset è parte della review.

### Ottimizzatore
- R9. Ciclo: leggi ultimi risultati e fallimenti per categoria → proponi una ipotesi (una sola modifica) → branch `hyp/<n>` → applica → eval → confronta.
- R10. Accetta solo se il pass rate totale sale **e** nessuna categoria scende (gate). Altrimenti rollback del branch.
- R11. Ogni iterazione scrive una riga nel `CHANGELOG.md`: ipotesi, esito, delta totale, delta per categoria, costo in euro.
- R12. Budget: costo per iterazione da Langfuse; stop quando il guadagno marginale per euro sulle ultime 3 iterazioni scende sotto `BUDGET_MIN_GAIN_PER_EUR`.
- R13. Tetto duro: `MAX_ITERATIONS` e `MAX_TOTAL_EUR`, entrambi in `.env`, entrambi nel results file.
- R14. Il pilota del loop è Claude Code via un prompt versionato in `src/optimizer/prompt.md`; deve essere sostituibile da un nodo LangGraph senza cambiare il resto.

### Feedback
- R15. `POST /feedback {trace_id, verdict, note}`; il caso viene ricostruito dalla traccia Langfuse, annotato e aggiunto al dataset con peso 2 e origine `feedback`.
- R16. Il README riporta quante iterazioni servono a recuperare un caso segnalato (metrica O4).

### Osservabilità e riproducibilità
- R17. Langfuse opzionale: senza chiavi tutto gira, senza tabella costi. Con chiavi: una traccia per run dell'agente, una per iterazione dell'ottimizzatore.
- R18. `just evals --seed 42` su stesso modello e stesso dataset riproduce gli stessi pass per caso. Se il provider non è deterministico, il README lo dichiara e riporta la varianza su 3 run.

## 7. Requisiti non funzionali

- Un'iterazione completa su 40 casi costa meno di 1 euro con un modello piccolo per l'agente sotto test. Il modello grande si usa solo per l'ottimizzatore e il giudice.
- Il repo si installa con `uv sync` e i test unitari passano senza chiavi.
- Nessun dato personale, nessun dato di clienti, nessun codice di datori di lavoro.

## 8. Metriche nel README (tutte da `evals/results/`)

1. Pass rate per iterazione, totale e per categoria.
2. Costo cumulato e guadagno marginale per euro; iterazione in cui scatta lo stop.
3. Ipotesi rifiutate dal gate per categoria, con un esempio.
4. Iterazioni per recuperare un caso da feedback.
5. Varianza su 3 run a seed fisso.

## 9. Milestone

| Giorno | Consegna | Criterio di done |
|---|---|---|
| 1 | Agente + dataset 40 casi + `evals/run.py` | Un results file reale, pass rate baseline nel README |
| 2 | Giudice + Langfuse + span di contesto | Costo per run visibile; casi `judge` valutati |
| 3 | Loop base con branch, keep/rollback, changelog | Prima curva pass rate per iterazione |
| 4 | Budget e gate per categoria | Uno stop per budget e un rifiuto per regressione documentati |
| 5 | Feedback endpoint e ingest pesato | Un caso segnalato recuperato |
| 6 | README finale, Origin, riproducibilità | Tre run a seed fisso, varianza riportata |

## 10. Rischi e decisioni prese

| Rischio | Decisione |
|---|---|
| Letto come copia di Nearform | Origin esplicito, nome diverso, tre estensioni misurabili in README |
| Loop che "impara" il dataset (overfitting ai 40 casi) | Split: 30 casi visibili all'ottimizzatore, 10 holdout riportati a parte. Il README mostra entrambi |
| Giudice LLM che premia risposte lunghe | Rubrica con penalità e casi `refusal` che premiano il rifiuto corretto |
| Costi API fuori controllo | R13, tetti duri in `.env` |
| Non determinismo del provider | R18, varianza dichiarata |

## 11. Domande aperte (per il grill)

1. L'ottimizzatore deve poter aggiungere casi al dataset? Oggi no (R8): rischio di dataset autoreferenziale contro utilità.
2. Il gate per categoria a tolleranza zero è troppo rigido con 10 casi per categoria? Una categoria oscilla di 10 punti per un caso solo.
3. Peso 2 al feedback: perché 2 e non 3, e chi decide quando un feedback è sbagliato?
4. Il giudice usa lo stesso modello dell'ottimizzatore: conflitto di interessi? Serve un modello diverso per giudicare?
5. Claude Code come pilota rende il loop non riproducibile al 100%: accettabile per il README, o serve il nodo LangGraph già dal giorno 3?
6. Il dominio ordini/clienti su SQLite è abbastanza "loro"? Alternativa: un dominio di documenti, più vicino ai loro casi enterprise, ma meno deterministico da valutare.
7. Quanto del loop va dichiarato "preso dal talk" e quanto è ovvio (Karpathy auto-research)? Il confine va scritto in Origin prima di pubblicare.
