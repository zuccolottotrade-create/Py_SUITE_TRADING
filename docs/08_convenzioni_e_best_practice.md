# 08. Convenzioni e best practice del progetto

## 08.1 Scopo

Questa sezione definisce le **convenzioni operative e le best practice obbligatorie**
per lo sviluppo, l’utilizzo e la manutenzione della Py_SUITE_TRADING.

Le regole qui descritte:
- hanno valore normativo all’interno del progetto;
- garantiscono coerenza, tracciabilità e riproducibilità;
- prevengono errori operativi e regressioni.

---

## 08.2 Principi generali

La Py_SUITE_TRADING si basa sui seguenti principi non negoziabili:

- **Determinismo**: a parità di input e configurazione, l’output deve essere identico.
- **Trasparenza**: ogni trasformazione del dato deve essere esplicita e ispezionabile.
- **Separazione delle responsabilità**: ogni modulo ha uno scopo preciso.
- **Fail-fast**: errori critici devono interrompere l’esecuzione.
- **No magia**: nessuna decisione implicita o nascosta.

---

## 08.3 Convenzioni sui dati

### Prefissi obbligatori

Ogni file CSV operativo deve utilizzare un prefisso standard:

- `RAW_` → dati grezzi
- `CLEAN_` → dati validati
- `KPI_` → dati arricchiti con indicatori
- `CLASSIFICAZIONE_OPERATIVA_` → contesto di mercato
- `STRATEGY_MAPPING_` → mapping strategico
- `STRATEGIA_` → regole operative
- `SIGNAL_` → segnali e stati
- `REPORT_` → output finale

L’uso di prefissi non standard è vietato.

---

### Regole sui CSV

- separatore: `;`
- separatore decimale: `,`
- header sempre presente
- una riga = una barra temporale

È vietato:
- modificare manualmente i CSV intermedi;
- riutilizzare file con prefisso errato;
- mescolare formati numerici.

---

## 08.4 Convenzioni sui moduli

- Ogni modulo deve essere **autonomo**.
- Ogni modulo deve:
  - validare i propri input;
  - produrre output espliciti;
  - fallire in modo chiaro in caso di errore.
- Un modulo non deve:
  - assumere stato persistente;
  - modificare output di altri moduli;
  - aggirare controlli a monte.

---

## 08.5 Convenzioni sulle strategie

- Le strategie devono essere **rule-based**.
- Nessuna logica strategica deve essere hard-coded.
- Tutte le strategie devono:
  - passare il Strategy QC Preflight;
  - essere completamente esplicite;
  - essere riproducibili nel tempo.

È vietato:
- adattare dinamicamente regole senza tracciabilità;
- modificare regole durante l’esecuzione;
- usare soglie “implicite”.

---

## 08.6 Convenzioni sulle configurazioni

- Le configurazioni sono parte del sistema.
- Ogni modifica a una configurazione deve:
  - essere versionata;
  - essere documentata;
  - rieseguire i controlli QC.

È consigliato:
- mantenere template separati dalle versioni operative;
- usare naming esplicito delle versioni.

---

## 08.7 Uso corretto di PIPELINE_MODE

- `PIPELINE_MODE=1` è destinato solo a esecuzioni automatizzate.
- In pipeline mode:
  - nessuna interazione utente è ammessa;
  - un errore interrompe l’intera esecuzione.
- Non è ammesso:
  - forzare input manuali;
  - silenziare errori critici.

---

## 08.8 Best practice di sviluppo

- Sviluppare e testare i moduli **singolarmente**.
- Usare dati piccoli e controllabili per il debug.
- Validare sempre dati e configurazioni prima del run completo.
- Non introdurre nuove funzionalità senza aggiornare la documentazione.

---

## 08.9 Manutenzione e evoluzione

Quando si introduce una modifica strutturale:

1. Aggiornare il codice.
2. Aggiornare la documentazione in `/docs`.
3. Verificare l’impatto sulla pipeline.
4. Rieseguire test manuali o automatici.

La documentazione e il codice devono evolvere insieme.

---

## 08.10 Regole di chiusura

La Py_SUITE_TRADING non è un sistema “adattivo” o “black box”.

È uno strumento:
- esplicito;
- controllabile;
- verificabile;
- orientato alla disciplina operativa.

Ogni deroga a queste regole deve essere **intenzionale, documentata e motivata**.
