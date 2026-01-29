# 04.08 Report Strategia

## 04.08.1 Scopo

Il modulo **Report Strategia** ha lo scopo di **trasformare i segnali e gli stati di posizione**
prodotti dal modulo Run Strategia in **report quantitativi di performance**.

Questo modulo:
- calcola metriche di performance;
- ricostruisce l’equity nel tempo;
- produce output finali destinati all’analisi.

Il modulo NON genera segnali e NON modifica la logica strategica.

---

## 04.08.2 Ambito

Il modulo opera:
- **a valle** di **04.07 Run Strategia**;
- come **fase finale** della pipeline Py_SUITE_TRADING.

È responsabile della **valutazione quantitativa dei risultati**, non delle decisioni operative.

---

## 04.08.3 Input

### File in input

- **Prefisso atteso**: `SIGNAL_`
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`

Il file di input contiene:
- segnali di ingresso e uscita;
- stato della posizione per ogni barra;
- dati OHLCV e KPI (ereditati a monte).

Il file deve provenire direttamente dal modulo Run Strategia.

---

### Selezione file

#### Modalità interattiva
- Directory di default: `_data/Test Data`
- Filtro: file con prefisso `SIGNAL_`

L’utente seleziona il file di segnali da analizzare.

#### Modalità pipeline
- Il file di input è determinato automaticamente.
- Nessuna interazione utente.

---

## 04.08.4 Output

### File prodotti

- **Prefisso prodotto**: `REPORT_`
- **Formato**: CSV (eventuali formati aggiuntivi sono opzionali)

Il file di report contiene:
- metriche di performance aggregate;
- risultati per trade;
- equity cumulata;
- statistiche di supporto.

---

### Naming convention

Il nome del file deve consentire di identificare:
- strumento;
- timeframe;
- strategia analizzata.

Esempio:
REPORT_FDAX_15M_SUPERTREND.csv


---

## 04.08.5 Flusso operativo

Il modulo esegue i seguenti passi:

1. Lettura del file `SIGNAL_`.
2. Identificazione delle operazioni (trade).
3. Calcolo dei profitti e delle perdite per trade.
4. Costruzione dell’equity nel tempo.
5. Calcolo delle metriche di performance.
6. Scrittura del file di report finale.

Il processo è deterministico e riproducibile.

---

## 04.08.6 Metriche di performance

Il modulo calcola tipicamente le seguenti metriche:

- numero totale di trade;
- trade vincenti e perdenti;
- profitto lordo e perdita lorda;
- profit factor;
- rendimento cumulato;
- drawdown massimo;
- durata media dei trade.

Le metriche calcolate sono configurabili e versionabili.

---

## 04.08.7 Modalità di esecuzione

### Interfaccia CLI

Il modulo è invocato tramite:
- menu della pipeline;
- runner dedicato;
- script `.command`.

---

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- esecuzione completamente automatica;
- output scritto in directory standard;
- nessuna richiesta di input all’utente.

Senza `PIPELINE_MODE`:
- selezione manuale del file `SIGNAL_`;
- conferma dei parametri di reporting.

---

## 04.08.8 Validazioni e controlli

Il modulo esegue i seguenti controlli:

- coerenza dei segnali ENTRY / EXIT;
- correttezza delle sequenze di trade;
- assenza di stati di posizione incoerenti;
- compatibilità temporale dei dati.

In caso di errore:
- l’esecuzione viene interrotta;
- non viene prodotto alcun file `REPORT_`.

---

## 04.08.9 Vincoli e limitazioni

Il modulo Report Strategia:

- NON modifica i segnali di input;
- NON ricalcola KPI o regole;
- NON fornisce raccomandazioni operative;
- NON esegue ottimizzazione dei parametri.

Il modulo assume che i segnali siano corretti e validati a monte.

---

## 04.08.10 Output atteso

Il file `REPORT_` rappresenta **l’output finale ufficiale** della Py_SUITE_TRADING.

È destinato a:
- analisi quantitativa;
- confronto tra strategie;
- archiviazione storica dei risultati.
