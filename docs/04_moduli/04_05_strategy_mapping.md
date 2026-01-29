# 04.05 Strategy Mapping

## 04.05.1 Scopo
Trasformare la classificazione operativa del mercato in una selezione strutturata di strategie applicabili.
# 04.05 Strategy Mapping

## 04.05.1 Scopo

Il modulo **Strategy Mapping** ha lo scopo di trasformare la **classificazione operativa del mercato** in una **selezione strutturata di strategie applicabili**.

Questo modulo:
- NON genera regole operative dettagliate;
- NON applica strategie ai dati storici;
- NON valuta performance.

Il risultato è un **mapping logico** tra contesto di mercato e strategie candidate.

---

## 04.05.2 Ambito

Il modulo opera **a valle della Classificazione Operativa** e **a monte della Rule Generation**.

È responsabile esclusivamente della **fase decisionale strategica ad alto livello**, ovvero:
- quali strategie sono compatibili con il contesto corrente;
- quali strategie sono prioritarie rispetto ad altre.

---

## 04.05.3 Input

### File in input

- **Prefisso atteso**: `CLASSIFICAZIONE_OPERATIVA_`
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`

Il file di input contiene:
- criteri di classificazione (es. liquidità, volatilità, direzionalità);
- etichette operative associate;
- motivazioni quantitative;
- metriche di supporto serializzate.

Il file NON contiene dati OHLCV completi.

---

### Selezione file

#### Modalità interattiva
- Directory di default: `_data/Test Data`
- Filtro: file con prefisso `CLASSIFICAZIONE_OPERATIVA_`

L’utente seleziona manualmente il file da processare.

#### Modalità pipeline
- Il file di input è determinato automaticamente dal flusso precedente.
- Nessuna interazione utente.

---

## 04.05.4 Output

### File prodotti

- **Prefisso prodotto**: `STRATEGY_MAPPING_`
- **Formato**: CSV

Il file di output contiene:
- elenco delle strategie candidate;
- informazioni di contesto operativo;
- eventuali ranking o priorità strategiche;
- metadati utili alla fase successiva.

Il file prodotto NON è direttamente utilizzabile da `run_strategia`.

---

### Naming convention

Il nome del file deve consentire di identificare chiaramente:
- lo strumento;
- il timeframe;
- la provenienza dalla classificazione operativa.

Esempio:
STRATEGY_MAPPING_FDAX_15M.csv


L’esecuzione può avvenire:
- in modo interattivo;
- come parte di una pipeline automatizzata.

---

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- l’esecuzione è non interattiva;
- i file di input/output sono determinati automaticamente;
- non è richiesto intervento dell’utente.

Senza `PIPELINE_MODE`:
- viene richiesta la selezione manuale dei file.

---

## 04.05.7 Validazioni e controlli

Il modulo esegue i seguenti controlli:

- presenza delle colonne obbligatorie;
- coerenza delle etichette operative;
- assenza di valori nulli critici;
- formato corretto dei campi.

In caso di errore:
- l’esecuzione viene interrotta;
- non viene prodotto alcun file di output.

---

## 04.05.8 Vincoli e limitazioni

Il modulo Strategy Mapping:

- NON accede ai dati OHLCV;
- NON genera regole ENTRY o EXIT;
- NON valuta risultati storici;
- NON modifica i dati di classificazione in input.

Il modulo assume che la classificazione operativa sia già validata a monte.

---

## 04.05.9 Errori tipici e risoluzione

**Errore: file di input non valido**
- Causa: file con prefisso errato o struttura incompleta.
- Azione: verificare che il file provenga dal modulo di Classificazione Operativa.

**Errore: nessuna strategia applicabile**
- Causa: contesto operativo non compatibile con le strategie disponibili.
- Azione: verificare i criteri di mapping o ampliare il set di strategie.

---

## 04.05.10 Output atteso

Il file prodotto da Strategy Mapping è destinato esclusivamente al modulo:

**04.06 Rule Generation**

Ogni utilizzo diretto del file da parte di altri moduli è da considerarsi non supportato.
