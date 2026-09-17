# Holdout confirmation on acceptance

Data: 2026-09-17. Stato: implementato nello stesso giorno, dimostrato dal loop 5.

## Problema

Il gate decide su un solo run di eval e il rumore misurato tra run è di un caso (README, "Variance"). L'holdout ha 10 casi: un caso è il 10%. L'ipotesi 12 è stata accettata con holdout 80% perché `F08` è passato in quel run; nei tre run successivi dello stesso prompt `F08` fallisce sempre. La regressione che il gate aveva bocciato quattro volte è passata alla quinta per estrazione fortunata.

## Decisione

Quando il gate dice sì, il loop rilancia **solo i 10 casi holdout** una seconda volta (circa $0.10) e accetta solo se anche il secondo run non scende sotto l'holdout del `main` corrente. Dopo l'accettazione, l'holdout di riferimento diventa il **minimo** dei due run: il confronto successivo usa il limite inferiore, non il colpo fortunato.

- Verdetto nel changelog: `rejected: holdout_confirm <secondo run> vs <riferimento>`.
- La riga del changelog mostra entrambi i delta: `+0.0pp (confirm -10.0pp)`.
- Il results file della conferma è committato come evidenza; il suo costo entra nell'iterazione e nel budget.
- Il loop file registra `holdout_confirm: {holdout, results_file, cost_eur}` per ogni ipotesi che ha superato il gate.

## Cosa non fa

Non ripete il run visible: il visible è stabile (29/30 pesati identici su tre run). Non conferma le ipotesi rifiutate: costano già zero in più. Non stima il rumore: usa la regola "due run su due", la più semplice che avrebbe fermato l'ipotesi 12.

## Misura

Numero di accettazioni ribaltate dalla conferma, nel README, dal loop file.
