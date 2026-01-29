# 06. PIPELINE_MODE e automazione

## 06.1 Scopo

Questa sezione definisce il funzionamento della Py_SUITE_TRADING in **modalità pipeline automatizzata**
e il ruolo della variabile di ambiente **PIPELINE_MODE**.

L’obiettivo è garantire:
- esecuzione ripetibile e non interattiva;
- integrazione tra moduli senza intervento manuale;
- comportamento coerente tra esecuzione manuale e orchestrata.

---

## 06.2 Concetto di PIPELINE_MODE

`PIPELINE_MODE` è una variabile di ambiente che controlla il **comportamento operativo** dei moduli.

Valori ammessi:

- `PIPELINE_MODE=1` → **modalità pipeline**
- `PIPELINE_MODE` assente o `0` → **modalità interattiva**

La variabile non modifica la logica di calcolo, ma **solo le modalità di input/output e interazione**.

---

## 06.3 Modalità interattiva (PIPELINE_MODE disattivo)

In modalità interattiva:

- l’utente seleziona manualmente i file di input;
- vengono mostrati menu, prompt e riepiloghi a video;
- l’utente conferma percorsi e parametri;
- i moduli possono essere eseguiti singolarmente.

Questa modalità è destinata a:
- sviluppo;
- debug;
- test manuali;
- analisi esplorativa.

---

## 06.4 Modalità pipeline (PIPELINE_MODE=1)

In modalità pipeline:

- nessun prompt interattivo è consentito;
- input e output sono determinati automaticamente;
- i moduli assumono che lo step precedente abbia prodotto output validi;
- eventuali errori interrompono l’esecuzione.

Questa modalità è destinata a:
- esecuzione end-to-end;
- automazione tramite launcher;
- esecuzioni batch ripetibili.

---

## 06.5 Comportamento dei moduli in PIPELINE_MODE

In `PIPELINE_MODE=1`, ogni modulo deve:

- disabilitare richieste di input all’utente;
- utilizzare directory e naming standard;
- fallire in modo esplicito in caso di errore;
- non richiedere conferme manuali.

I moduli NON devono:
- cambiare logica di calcolo;
- modificare soglie o parametri impliciti;
- silenziare errori critici.

---

## 06.6 Orchestrazione tramite launcher `.command`

I launcher `.command` (macOS) hanno il ruolo di:

- impostare `PIPELINE_MODE=1`;
- attivare l’ambiente virtuale corretto;
- eseguire i moduli nell’ordine previsto;
- gestire il ritorno al menu o al sistema.

Il launcher NON deve:
- implementare logica di business;
- sostituire la validazione dei moduli;
- manipolare direttamente i dati.

---

## 06.7 Sequenza tipica in modalità pipeline

Una sequenza tipica orchestrata è:

1. Estrazione dati
2. Controllo coerenza dati
3. Calcolo KPI
4. Classificazione Operativa
5. Strategy Mapping
6. Rule Generation
7. Run Strategia
8. Report Strategia

Ogni step utilizza esclusivamente l’output dello step precedente.

---

## 06.8 Gestione degli errori in pipeline

In modalità pipeline:

- un errore in un modulo interrompe la sequenza;
- non vengono eseguiti moduli successivi;
- non vengono prodotti output parziali non validi.

Il comportamento “fail-fast” è una scelta progettuale deliberata.

---

## 06.9 Variabili di ambiente rilevanti

Oltre a `PIPELINE_MODE`, possono essere utilizzate variabili come:

- directory dati predefinite;
- flag di debug;
- selezione ambiente (test / produzione).

Tutte le variabili di ambiente devono:
- avere un valore di default sicuro;
- essere documentate;
- non alterare silenziosamente il comportamento dei moduli.

---

## 06.10 Vincoli e best practice

- Non mescolare modalità interattiva e pipeline nella stessa esecuzione.
- Non forzare input manuali in `PIPELINE_MODE=1`.
- Testare sempre i moduli in modalità interattiva prima dell’automazione.
- Documentare ogni nuova variabile di ambiente introdotta.

---

## 06.11 Output atteso

Con `PIPELINE_MODE=1`, la Py_SUITE_TRADING deve produrre:

- una sequenza completa di file intermedi;
- un output finale `REPORT_*.csv`;
- nessuna richiesta di intervento manuale.

Il comportamento deve essere ripetibile e verificabile.
