# 03. Formato e flusso dei dati (CSV)

## 03.1 Ruolo centrale del formato CSV

All’interno della Py_SUITE_TRADING il formato CSV rappresenta **l’unico formato di scambio dati** tra i moduli.

Ogni modulo:
- riceve uno o più file CSV in input;
- produce uno o più file CSV in output;
- non mantiene stato interno persistente.

Il CSV è considerato **fonte di verità operativa** per ogni fase della pipeline.

---

## 03.2 Standard CSV adottato

Tutti i file CSV prodotti e consumati dalla suite devono rispettare il seguente standard:

- **Separatore di campo**: `;` (punto e virgola)
- **Separatore decimale**: `,` (virgola)
- **Encoding**: UTF-8
- **Header**: sempre presente
- **Una riga = una barra temporale**

Non sono ammessi:
- separatori alternativi;
- CSV senza intestazione;
- modifiche manuali ai file intermedi.

---

## 03.3 Colonne temporali

Ogni file CSV contenente dati di mercato deve includere una colonna temporale primaria.

Caratteristiche:
- timestamp univoco per riga;
- ordinamento cronologico crescente;
- assenza di duplicati.

La colonna temporale:
- non viene mai modificata dai moduli successivi;
- rappresenta l’asse temporale comune a tutta la pipeline.

---

## 03.4 Colonne OHLCV

I dati di mercato sono rappresentati tramite colonne OHLCV standard:

- `open`
- `high`
- `low`
- `close`
- `volume`

Requisiti operativi:
- `high >= max(open, close)`
- `low <= min(open, close)`
- `volume >= 0`

Eventuali violazioni sono gestite dal modulo di controllo coerenza.

---

## 03.5 Colonne KPI e metriche derivate

I moduli di calcolo KPI aggiungono colonne derivate al CSV originale.

Caratteristiche:
- le colonne KPI non sostituiscono mai le colonne OHLCV;
- ogni KPI occupa una colonna dedicata;
- i nomi delle colonne sono espliciti e stabili nel tempo.

Le colonne KPI:
- possono contenere valori nulli nelle prime barre;
- non devono alterare la struttura temporale del file.

---

## 03.6 File di classificazione operativa

I file di classificazione operativa contengono informazioni derivate dall’analisi quantitativa del contesto di mercato.

Struttura tipica:
- una riga per criterio di classificazione;
- etichette operative (es. bassa, media, alta);
- motivazioni quantitative;
- metriche di supporto serializzate.

Questi file non contengono dati OHLCV completi e non sono utilizzabili direttamente per il calcolo dei segnali.

---

## 03.7 File di strategia e segnali

I file prodotti dai moduli di strategia includono:

- segnali di ingresso e uscita;
- stato della posizione;
- eventuali colonne di supporto alla logica decisionale.

Caratteristiche:
- la struttura temporale è mantenuta;
- le colonne strategiche sono aggiuntive;
- non vengono rimossi dati storici.

---

## 03.8 Prefissi dei file e flusso operativo

Il flusso dei CSV è regolato da prefissi convenzionati che identificano lo stato del dato:

- `RAW_` → dati grezzi appena estratti
- `CLEAN_` → dati validati e coerenti
- `QC_` → report di controllo qualità
- `CLASSIFICAZIONE_` → output di classificazione operativa
- `STRATEGIA_` → output di strategia e segnali
- `REPORT_` → output di reporting finale

I moduli operano esclusivamente sui prefissi previsti.

---

## 03.9 Tracciabilità e riproducibilità

Ogni trasformazione dei dati:
- è esplicita;
- è contenuta in un file CSV;
- può essere archiviata e confrontata nel tempo.

La Py_SUITE_TRADING non modifica mai un file CSV in-place senza produrne una nuova versione identificabile.

---

## 03.10 Vincoli operativi

Sono vietate le seguenti pratiche:

- modifica manuale dei CSV intermedi;
- riutilizzo di file con prefisso errato;
- mescolanza di separatori o formati numerici;
- eliminazione selettiva di righe temporali.

Il rispetto di questi vincoli è essenziale per garantire la correttezza dell’intera pipeline.
