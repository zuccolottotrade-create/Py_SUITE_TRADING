# 04.07 Run Strategia

## 04.07.1 Scopo

Il modulo **Run Strategia** ha lo scopo di **applicare le regole operative generate a monte**
ai dati storici di mercato, producendo segnali, stati di posizione e risultati intermedi
necessari alla fase di reporting.

Questo modulo:
- applica regole ENTRY / EXIT / FILTRO;
- gestisce lo stato della posizione nel tempo;
- produce output strutturati per il reporting.

Il modulo NON genera strategie e NON produce report di performance finali.

---

## 04.07.2 Ambito

Il modulo opera:
- **a valle** di **04.06 Rule Generation**;
- **a monte** di **04.08 Report Strategia**.

È il **cuore esecutivo** della Py_SUITE_TRADING, dove le regole diventano segnali.

---

## 04.07.3 Input

### File in input

Il modulo richiede due tipologie di input:

#### 1. File dati OHLCV + KPI
- **Prefisso atteso**: `CLEAN_`
- **Formato**: CSV
- **Contenuto**: OHLCV + colonne KPI

Il file deve provenire dal modulo **PyKPI_calcolo**.

#### 2. File regole strategiche
- **Prefisso atteso**: `STRATEGIA_`
- **Formato**: CSV
- **Contenuto**: regole ENTRY, EXIT, filtri, parametri

---

### Selezione file

#### Modalità interattiva
- Directory di default: `_data/Test Data`
- L’utente seleziona:
  1. il file `CLEAN_*.csv`
  2. il file `STRATEGIA_*.csv`

#### Modalità pipeline
- I file sono determinati automaticamente dalla pipeline.
- Nessuna interazione utente.

---

## 04.07.4 Output

### File prodotti

- **Prefisso prodotto**: `SIGNAL_`
- **Formato**: CSV

Il file di output contiene:
- segnali di ingresso e uscita;
- stato della posizione (flat / long / short);
- colonne di supporto alla logica;
- dati temporali invariati.

---

### Naming convention

Il nome del file deve consentire di identificare:
- strumento;
- timeframe;
- strategia applicata.

Esempio:
SIGNAL_FDAX_15M_SUPERTREND.csv


---

## 04.07.5 Flusso operativo

Il modulo esegue i seguenti passi:

1. Lettura del file dati OHLCV + KPI.
2. Lettura del file di regole strategiche.
3. Validazione della compatibilità dati–regole.
4. Inizializzazione dello stato della posizione.
5. Iterazione sequenziale sulle barre temporali.
6. Valutazione delle condizioni ENTRY / EXIT.
7. Aggiornamento dello stato di posizione.
8. Scrittura del file di segnali.

L’elaborazione è **sequenziale e deterministica**.

---

## 04.07.6 Gestione della posizione

Il modulo gestisce internamente:
- stato corrente (flat, long, short);
- transizioni di stato;
- prevenzione di stati incoerenti.

Non sono consentite:
- posizioni multiple simultanee;
- aperture senza chiusura precedente;
- salti di stato non espliciti.

---

## 04.07.7 Modalità di esecuzione

### Interfaccia CLI

Il modulo è invocato tramite:
- menu della pipeline;
- runner dedicato;
- script `.command`.

---

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- nessuna richiesta di input interattivo;
- esecuzione completamente automatica;
- output scritto in directory standard.

Senza `PIPELINE_MODE`:
- selezione manuale dei file;
- conferma dei parametri operativi.

---

## 04.07.8 Validazioni e controlli

Il modulo esegue i seguenti controlli:

- presenza delle colonne KPI richieste;
- validità delle regole operative;
- coerenza temporale dei dati;
- compatibilità tra timeframe dati e regole.

In caso di errore:
- l’esecuzione viene interrotta;
- non viene prodotto alcun file `SIGNAL_`.

---

## 04.07.9 Vincoli e limitazioni

Il modulo Run Strategia:

- NON calcola metriche di performance;
- NON modifica i dati OHLCV;
- NON apprende o adatta le regole;
- NON esegue trading reale.

Il modulo assume che i dati e le regole siano già validati a monte.

---

## 04.07.10 Output atteso

Il file `SIGNAL_` prodotto è destinato esclusivamente al modulo:

**04.08 Report Strategia**

Ogni utilizzo diretto per scopi diversi è da considerarsi non supportato.
