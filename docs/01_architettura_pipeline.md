# 01. Architettura generale della Pipeline

## 01.1 Visione d’insieme della pipeline

La Py_SUITE_TRADING è organizzata come una **pipeline sequenziale di moduli indipendenti**.  
Ogni modulo riceve in input i risultati del modulo precedente e produce un output strutturato, destinato a essere consumato dal modulo successivo.

La pipeline è progettata per:
- essere eseguita integralmente oppure per singoli step;
- garantire tracciabilità completa dei dati;
- consentire controlli intermedi e ispezione manuale.

La sequenza logica della pipeline è la seguente:

1. Estrazione dei dati
2. Controllo di coerenza dei dati
3. Calcolo degli indicatori (KPI)
4. Classificazione operativa
5. Mapping e costruzione delle regole
6. Esecuzione della strategia
7. Produzione dei report

---

## 01.2 Sequenza dei moduli

La pipeline completa segue l’ordine sotto riportato:

ESTRAZIONE_PRO
↓
CONTROLLO_COERENZA_DATI
↓
PYKPI_CALCOLO
↓
CLASSIFICAZIONE_OPERATIVA
↓
STRATEGY_MAPPER
↓
RUN_STRATEGIA
↓
REPORT_STRATEGIA


Ogni modulo:
- opera su file CSV;
- produce output con naming convenzionato;
- non dipende dallo stato interno di altri moduli.

---

## 01.3 Responsabilità dei singoli moduli

### Estrazione_pro
Responsabile dell’ottenimento dei dati OHLCV da fonti esterne.  
Produce file di dati grezzi strutturati.

Non esegue alcuna validazione avanzata sui dati.

---

### Controllo_coerenza_dati
Responsabile della verifica della qualità e coerenza dei dati di mercato.

Esegue controlli quali:
- timestamp duplicati;
- valori OHLC non validi;
- dati mancanti o anomali.

Produce file classificati come:
- dati accettati;
- dati scartati;
- report di controllo qualità.

---

### PyKPI_calcolo
Responsabile del calcolo degli indicatori tecnici e delle metriche quantitative.

Opera esclusivamente su dati validati.  
Non prende decisioni strategiche.

---

### Classificazione Operativa
Responsabile dell’analisi del contesto di mercato.

Attribuisce etichette operative (es. liquidità, volatilità, direzionalità) sulla base di criteri quantitativi.

Produce file di classificazione utilizzabili per la costruzione delle strategie.

---

### Strategy Mapper
Responsabile della trasformazione delle classificazioni operative in strutture di regole utilizzabili dalla strategia.

Costruisce:
- regole di ingresso;
- regole di uscita;
- vincoli operativi.

Non esegue alcun calcolo di performance.

---

### Run Strategia
Responsabile dell’applicazione delle regole strategiche ai dati storici.

Genera:
- segnali di ingresso e uscita;
- posizioni;
- risultati intermedi della strategia.

---

### Report Strategia
Responsabile della produzione dei report finali.

Calcola metriche di performance e produce output di sintesi destinati all’analisi.

---

## 01.4 Modalità di esecuzione della pipeline

La pipeline può essere eseguita in due modalità principali:

- **Modalità interattiva**  
  L’utente seleziona manualmente i file di input e conferma le operazioni.

- **Modalità pipeline**  
  L’esecuzione avviene in modo automatizzato, senza interazioni, tramite variabili di ambiente e script di orchestrazione.

La modalità operativa è controllata dal parametro di ambiente `PIPELINE_MODE`.

---

## 01.5 Gestione degli errori e interruzioni

Ogni modulo è responsabile della validazione dei propri input.

In caso di errore:
- l’esecuzione del modulo viene interrotta;
- l’errore viene segnalato in modo esplicito;
- non vengono prodotti output parziali non validi.

La pipeline non tenta di recuperare automaticamente errori strutturali sui dati o sulle configurazioni.

---

## 01.6 Garanzie della pipeline

La Py_SUITE_TRADING garantisce che:

- ogni output è riconducibile a uno specifico input;
- le trasformazioni dei dati sono deterministiche;
- i file intermedi possono essere archiviati e confrontati nel tempo;
- l’utente mantiene il controllo esplicito delle decisioni strategiche.

---

## 01.7 Limitazioni intenzionali

La pipeline non è progettata per:

- elaborazioni in tempo reale;
- esecuzione asincrona dei moduli;
- gestione di flussi dati continui;
- adattamento automatico delle strategie.

Queste limitazioni sono scelte progettuali deliberate.
