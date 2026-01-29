# 00. Concetti base e visione della Py_SUITE_TRADING

## 00.1 Scopo della Suite

La **Py_SUITE_TRADING** è una suite software modulare progettata per l’analisi quantitativa di strumenti finanziari e per la generazione di segnali di trading basati su regole esplicite e verificabili.

Lo scopo principale della suite è:
- trasformare dati di mercato OHLCV in informazioni operative strutturate;
- applicare criteri quantitativi e regole di strategia definite dall’utente;
- produrre output ripetibili, tracciabili e verificabili nel tempo.

La suite è orientata a un utilizzo **operativo e analitico**, non sperimentale.

---

## 00.2 Principi di progettazione

La Py_SUITE_TRADING è costruita secondo i seguenti principi fondamentali:

### Separazione delle responsabilità
Ogni modulo della suite ha una responsabilità unica e ben definita.  
Un modulo:
- riceve un input specifico;
- esegue un insieme limitato di operazioni;
- produce un output deterministico.

Non sono previste sovrapposizioni funzionali tra i moduli.

### Pipeline deterministica
La suite opera come una pipeline sequenziale.  
A parità di input e configurazione, l’output prodotto è sempre identico.

Non sono presenti componenti stocastiche o auto-adattive.

### Centralità del dato
Il dato di mercato e le sue trasformazioni sono sempre rappresentati in forma tabellare (CSV).  
Ogni passaggio intermedio è ispezionabile e archiviabile.

### Configurazione esterna
Le regole operative e strategiche non sono hard-coded nel codice.  
Le decisioni di trading sono definite tramite file di configurazione esterni, principalmente in formato Excel o CSV.

### Verificabilità e controllo qualità
Prima dell’esecuzione delle strategie, la suite prevede controlli di coerenza e validazione dei dati e delle configurazioni.

---

## 00.3 Ambito di utilizzo

La Py_SUITE_TRADING è progettata per:

- analisi quantitativa su dati storici;
- backtesting di strategie rule-based;
- supporto alla costruzione di strategie operative;
- produzione di report quantitativi strutturati.

Gli strumenti finanziari tipicamente supportati includono:
- ETF;
- futures;
- indici;
- strumenti con dati OHLCV standardizzati.

La suite è utilizzabile sia in modalità **interattiva** sia in modalità **pipeline automatizzata**.

---

## 00.4 Cosa fa la Suite

La Py_SUITE_TRADING consente di:

- estrarre dati di mercato da fonti esterne;
- verificare la coerenza e la qualità dei dati;
- calcolare indicatori tecnici e metriche quantitative;
- classificare il contesto operativo del mercato;
- generare segnali di ingresso e uscita basati su regole;
- produrre report di performance e riepilogo.

Ogni fase del processo produce file intermedi chiaramente identificabili.

---

## 00.5 Cosa NON fa la Suite

La Py_SUITE_TRADING:

- non esegue trading automatico in tempo reale;
- non prende decisioni autonome non definite dall’utente;
- non utilizza modelli di machine learning auto-adattivi;
- non modifica i dati di input senza tracciabilità;
- non fornisce raccomandazioni di investimento.

La suite è uno strumento di **analisi e supporto decisionale**, non un sistema di esecuzione.

---

## 00.6 Utenti di riferimento

La Py_SUITE_TRADING è destinata a:

- analisti quantitativi;
- trader sistematici;
- sviluppatori di strategie rule-based;
- utenti tecnici con familiarità con dati finanziari e scripting.

L’utilizzo presuppone una conoscenza di base dei concetti di mercato finanziario e dei dati OHLCV.
