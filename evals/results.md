# Evaluation Results

Documents evaluated: 6
Extractor model: gemma3:4b
Dataset profile: 3 clean, 3 messy_scanned
Synthetic documents: 6
Hallucination rate: 0.0% (0/46 non-null fields)
Caught rate: N/A (no wrong fields in the labeled set)
Decision accuracy: 100.0% (6/6)
Decision mix: 2 auto_approve, 2 human_review, 2 amendment_request

Note: Messy samples are rasterized PDFs with an invisible searchable text layer for grounding checks. This run does not measure OCR on image-only documents.

| Field | Exact accuracy | Normalized accuracy |
| --- | ---: | ---: |
| consignee_name | 100.0% | 100.0% |
| hs_code | 100.0% | 100.0% |
| port_of_loading | 100.0% | 100.0% |
| port_of_discharge | 100.0% | 100.0% |
| incoterms | 100.0% | 100.0% |
| goods_description | 100.0% | 100.0% |
| gross_weight | 100.0% | 100.0% |
| invoice_number | 100.0% | 100.0% |
