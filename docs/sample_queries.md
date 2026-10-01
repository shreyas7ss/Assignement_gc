# Sample NL Queries

These two questions were sent through `answer_question()` against `.data/demo/pipeline.sqlite` while Gemini was the NL-to-SQL provider. They are historical examples; the SQL shown is the guarded SQL actually executed and rows are the raw SQLite results. The current provider is local Ollama.

## Approved Count

Question: `How many shipments have the auto-approve decision?`

```sql
SELECT * FROM (SELECT count(id) FROM shipments WHERE decision = 'auto_approve') AS guarded_query LIMIT 100
```

Answer: 1 shipment.

Raw rows:

```json
[{"count(id)": 1}]
```

## Amendment Detail

Question: `For the shipment with decision amendment_request, return its document name and fields.found where fields.field is consignee_name.`

```sql
SELECT * FROM (SELECT T1.doc_name, T2.found FROM shipments AS T1 INNER JOIN fields AS T2 ON T1.id = T2.shipment_id WHERE T1.decision = 'amendment_request' AND T2.field = 'consignee_name') AS guarded_query LIMIT 100
```

Answer: `messy_scanned_invoice.pdf` had the found consignee value `ACME Trading Co.`.

Raw rows:

```json
[{"doc_name": "messy_scanned_invoice.pdf", "found": "ACME Trading Co."}]
```
