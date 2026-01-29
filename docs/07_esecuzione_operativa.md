# 07. Esecuzione operativa

## 07.1 Scopo

Questa sezione descrive **le modalità operative concrete** per utilizzare la Py_SUITE_TRADING:
- esecuzione dei singoli moduli;
- esecuzione end-to-end della pipeline;
- uso tramite menu, CLI e launcher `.command`;
- gestione degli errori più comuni.

La sezione è pensata come **guida pratica** per l’uso quotidiano della suite.

---

## 07.2 Modalità di esecuzione disponibili

La Py_SUITE_TRADING può essere utilizzata in tre modalità principali:

1. **Esecuzione interattiva da menu**
2. **Esecuzione manuale via CLI**
3. **Esecuzione automatizzata tramite launcher**

Le tre modalità sono equivalenti in termini di logica di calcolo, ma differiscono per livello di automazione.

---

## 07.3 Esecuzione tramite menu interattivo

### Descrizione

La modalità menu fornisce un’interfaccia guidata che consente di:
- selezionare i moduli da eseguire;
- scegliere i file di input;
- visualizzare riepiloghi e messaggi di stato.

È la modalità consigliata per:
- prime esecuzioni;
- debug;
- verifica dei risultati intermedi.

---

### Flusso tipico

1. Avvio del menu principale.
2. Selezione del modulo o della pipeline completa.
3. Selezione interattiva dei file di input.
4. Conferma dell’esecuzione.
5. Visualizzazione dell’esito a video.

---

## 07.4 Esecuzione manuale via CLI

### Descrizione

Ogni modulo può essere eseguito direttamente tramite riga di comando (CLI),
senza passare dal menu.

Questa modalità è utile per:
- test mirati;
- integrazione con script esterni;
- debug puntuale di un singolo step.

---

### Esempi operativi

Esecuzione di un modulo (esempio generico): 
python -m <modulo>.cli


Esecuzione con parametri espliciti (se supportati):
python -m <modulo>.cli --input <file> --output <file>


I parametri disponibili dipendono dal modulo specifico.

---

## 07.5 Esecuzione automatizzata tramite launcher

### Descrizione

I launcher `.command` (macOS) consentono l’esecuzione **completamente automatizzata**
della pipeline o di sue parti.

Il launcher:
- attiva l’ambiente virtuale corretto;
- imposta `PIPELINE_MODE=1`;
- esegue i moduli in sequenza;
- gestisce il ritorno al menu o al sistema.

---

### Uso tipico

1. Doppio click sul file `.command`.
2. Avvio automatico della pipeline.
3. Nessuna richiesta di input manuale.
4. Produzione dell’output finale (`REPORT_`).

Questa modalità è destinata a:
- esecuzioni ripetibili;
- batch di analisi;
- uso operativo standard.

---

## 07.6 Esecuzione della pipeline completa

### Sequenza standard

L’esecuzione completa della pipeline segue l’ordine:

1. Estrazione dati
2. Controllo coerenza dati
3. Calcolo KPI
4. Classificazione Operativa
5. Strategy Mapping
6. Rule Generation
7. Run Strategia
8. Report Strategia

Ogni step utilizza l’output del precedente.

---

### Output atteso

Al termine dell’esecuzione completa devono essere presenti:
- tutti i file intermedi previsti;
- un file `REPORT_*.csv` come output finale;
- nessun errore bloccante.

---

## 07.7 Uso di PIPELINE_MODE in esecuzione operativa

- In modalità interattiva (`PIPELINE_MODE` disattivo):
  - l’utente controlla ogni input;
  - è possibile interrompere o ripetere singoli step.

- In modalità pipeline (`PIPELINE_MODE=1`):
  - nessuna interazione è consentita;
  - un errore interrompe l’intera sequenza;
  - il comportamento è deterministico.

Non è ammesso mescolare le due modalità nella stessa esecuzione.

---

## 07.8 Gestione degli output

### Directory standard

Tutti gli output sono scritti sotto:
- `_data/`
- tipicamente in `_data/Test Data` per esecuzioni manuali.

Gli output devono essere identificabili tramite:
- prefisso (`RAW_`, `CLEAN_`, `KPI_`, `CLASSIFICAZIONE_`, `STRATEGIA_`, `SIGNAL_`, `REPORT_`);
- naming coerente con strumento e timeframe.

---

## 07.9 Troubleshooting operativo

### Errore: nessun file di input selezionabile
- Causa: directory errata o prefisso non corretto.
- Azione: verificare che il file atteso esista e abbia il prefisso giusto.

---

### Errore: pipeline interrotta senza output finale
- Causa: errore bloccante in uno dei moduli.
- Azione: rieseguire il modulo fallito in modalità interattiva per analisi.

---

### Errore: output incoerente o incompleto
- Causa: configurazione non validata o dati non CLEAN.
- Azione: verificare QC dei dati e Strategy QC Preflight.

---

## 07.10 Best practice operative

- Eseguire sempre i moduli a monte prima di quelli a valle.
- Non saltare il controllo di coerenza dati.
- Conservare gli output intermedi per tracciabilità.
- Versionare configurazioni e documentazione insieme al codice.
- Usare la modalità interattiva prima dell’automazione completa.

---

## 07.11 Output atteso

Un’esecuzione corretta della Py_SUITE_TRADING produce:
- output intermedi coerenti;
- un output finale `REPORT_*.csv`;
- risultati ripetibili a parità di dati e configurazioni.
