# Nova Trade-Document Pipeline: PRD

Shreyas · Part 1

> Items marked **[UPDATE]** need your real numbers after the Ollama rerun. Delete this note before submitting.

---

## 1. What I understood about Nova

**[YOUR TURN. Write this yourself, max 200 words per question. See the notes in the chat reply.]**

---

## 2. Problem statement

### Where the current flow breaks

Right now a person opens each emailed PDF, reads the fields, and compares them with what the customer wants. That works until it doesn't, and it tends to break in the same few places:

- **The rules aren't written anywhere.** What a customer requires often lives in a senior operator's head. A new hire learns it by making mistakes, and the mistakes reach the customer as cargo holds or customs delays.
- **Small errors are easy to miss.** One wrong digit in an HS code or a consignee spelled slightly differently looks fine at the end of a long day.
- **A missing field can look like a fine one.** If nobody notices an Incoterm is absent, the document moves on.
- **Every fix costs a round trip.** CG spots one problem, emails SU, SU fixes it and resends, and CG finds a second problem. Two to four cycles per shipment is normal, and each one adds 4 to 24 hours.
- **Amendment emails are typed by hand.** They're inconsistent and sometimes incomplete, which causes the next cycle.
- **There's no record.** Nobody can quickly say how many documents are waiting, or why one was approved three weeks ago.

I haven't seen GoComet's real numbers for any of this, so I'm treating these as the failure modes to test with real operators, not as measured facts.

### What success looks like in the first five minutes

A CG operator uploads a document. Within a minute or two they see the eight fields the system read, how sure it is about each, and which ones match the customer's rules, which don't, and which it couldn't be sure about. For mismatches they see what was found next to what was expected. At the bottom is a decision (approve, review, or amendment) with a reason in plain words. If the system wasn't sure about something, it says so, and that document goes to a human. The operator should know in about ten seconds whether they need to do anything.

---

## 3. Users and jobs to be done

**Meera, CG operator.** She validates document sets all day. She cares about catching the errors that cause real problems, getting through the queue faster, and being able to explain a decision if anyone questions it later. Her frustrations are re-reading every field and retyping amendment emails.

**Arjun, SU documentation contact.** He prepares the paperwork at the supplier and sends it off. He wants to know exactly what's wrong in one message, so he can fix everything at once instead of discovering problems one round at a time.

Jobs to be done:

1. When a new document arrives, I (Meera) want the key fields already extracted with a confidence score, so that I'm checking the results instead of typing them out.
2. When a value breaks a customer rule, I want to see what was found next to what was expected, so that I can confirm the problem in a few seconds.
3. When the system can't read a field clearly, I want it flagged as uncertain instead of guessed, so that a wrong value never slips through as approved.
4. When a document has several problems, I want one amendment draft listing every one of them, so that Arjun can fix them all in a single round.
5. When someone asks why a shipment was approved or held, I want to look up the stored decision and its reasoning, so that I can answer without digging through email.
6. When my manager wants a quick picture, I want to ask "how many shipments were flagged this week?" in plain language, so that nobody has to write a query.

---

## 4. Agent architecture

### Why three, and not one or five

The three stages fail in three different ways, so I kept them separate.

- **Reading the document** is a perception problem. The model can misread a blurry digit or invent something.
- **Checking against the rules** is a logic problem. It should be exact and repeatable, and it doesn't need a language model to decide whether two values match.
- **Deciding what to do** is a policy problem: approve, ask a human, or ask the supplier to fix it.

If I put all of that into one prompt, I couldn't tell which part went wrong, I couldn't retry only the reading step, and the same model that read the document would also be judging whether its own reading was good. That's the exact failure the system is meant to prevent. I didn't go to five agents because splitting further (one per field, or a separate agent just to write the explanation) adds handoffs without adding a new kind of failure to defend against.

### What each one does

| Agent | Role | Input | Output |
|---|---|---|---|
| Extractor | Executor | PDF or image (up to 3 pages) | Eight fields, each with a value, a confidence score, a supporting quote, and a page number |
| Validator | Verifier | The extraction and the customer's rule file | Per field: match, mismatch (with found and expected), or uncertain |
| Router | Decider | The validation result | One of auto_approve, human_review, or amendment_request, with written reasoning and, where needed, a draft |

The Validator and Router are deliberately plain Python. They're still separate stages with their own inputs and outputs, so I count them as agents in the architecture, but no model is allowed to approve its own reading.

### How they talk to each other

Typed Pydantic objects pass between stages inside a LangGraph state. Nothing is handed over as free text, so a stage either receives a well-formed object or it fails clearly.

### Surviving a crash

LangGraph saves the state to a SQLite checkpoint after every completed step, keyed by the run ID. If the process dies halfway, running it again with the same ID picks up from the last finished step. **[UPDATE: add one line on what happened when you killed a run mid-way.]**

---

## 5. LLM and tooling choices

**Extractor model.** I run `qwen3-vl:8b` locally through Ollama. I started on Gemini's free tier, but I hit a real request quota limit during testing (20 requests on the model I was using), and a separate provider blocked my requests at the network edge. Running locally removed both problems and keeps documents on the machine. The tradeoff is that an 8-billion-parameter model is likely to be less accurate on messy scans than a top hosted model, and it's slower on a laptop. **[UPDATE: add your measured accuracy and latency here.]** For production I'd evaluate a stronger hosted vision model on the same test set and choose based on accuracy, cost, and latency.

**Text-to-SQL model.** `qwen3:8b`, also local. The queries are short and structured, so a small model is enough. Its output is never trusted directly: a guard only allows a single SELECT on the app's own tables, on a read-only connection, with a row limit.

**Validator and Router.** No model. These decisions have to be exact and explainable, and code gives me that.

**Bad-quality documents.** The Extractor gets a cleaned-up image, one retry at most, and then anything it can't back up is set to null and sent to human review. **[UPDATE: once Tesseract is installed, describe the image-only path here and how it was tested. Right now scanned images without a text layer fail on purpose instead of being approved.]**

**Orchestration.** LangGraph. Nova is built on it, it gives me checkpointing and conditional routing without writing my own state machine, and the graph here is small enough that I can explain every node. A hand-written state machine would have worked too, but I would have had to build the resume logic myself.

**Structured output.** I use it where the model has to produce data: the Extractor's fields and the SQL statement. I avoid it for decisions. Whether a document is approved is never a model output.

**Storage.** SQLite. It runs on a laptop with no setup. In production I'd expect ClickHouse for analytics, as the JD describes.

**Retrieval (RAG).** Not used. One customer's rules fit in a small YAML file, and the natural-language questions need exact counts, which text-to-SQL does better than vector search.

---

## 6. Trust, failure handling, and evals

**Stopping made-up fields.** The Extractor must return null when a field isn't in the document. Every non-null value has to come with a quote, and the pipeline checks that the quote really appears in the document's text. If it doesn't, the extractor tries once more. If it still can't support the value, the value is removed and its confidence set to zero. A test covers this case, but it's a test fixture and not a failure I saw live.

**Low-confidence fields.** Confidence is range-checked, and format checks (for example, whether an HS code looks like one) can push a field to uncertain. Any uncertain or missing field sends the document to human review. There's no path from an uncertain field to auto-approval.

**Loops and runaway cost.** At most one extraction retry, a three-page cap per document, and errors that are returned and stored instead of hidden. Token counts are recorded on successful runs. I have not configured prices yet, so I'm not claiming a dollar cost per document. **[UPDATE: if you add a per-document cost cap, say so here.]**

**Offline eval.** A labeled set of six documents scored by plain code: field accuracy after normalization, hallucination rate (values not in the document), decision accuracy, and how often a wrong field was caught as uncertain or mismatched. The first run, on Gemini, got 100% field accuracy, 0 of 46 non-null values hallucinated, and 6 of 6 decisions correct. That set is small and synthetic, and three of the "messy" files still have a hidden text layer, so I read it as a smoke test and not as proof. **[UPDATE: replace with Ollama results, and add documents with deliberately seeded errors so the caught-rate is actually measured.]**

**Online metric.** The share of auto-approved documents that a human later overrides. If that number isn't near zero, the system is approving things it shouldn't.

---

## 7. Metrics and success criteria

**North star:** the share of documents where the CG operator accepts the agent's decision without changing it.

**Supporting metrics**

| Kind | Metric |
|---|---|
| Agent quality | Field accuracy on the critical fields (consignee, HS code, Incoterms) |
| Agent quality | Hallucination rate |
| Agent quality | Caught rate: wrong fields flagged uncertain or mismatch |
| Trust | False auto-approvals (target: zero) |
| System health | p50 and p95 time from upload to decision |
| System health | Share of runs that fail outright |
| Business | Share of documents sent to human review |
| Business | Median time to decision, and amendment cycles per shipment |

**Go for a two-week pilot with one customer if:**
- no wrongly approved document reaches the customer,
- critical-field accuracy is at least 95% on the customer's own labeled documents,
- hallucination is under 1%,
- operators accept at least 60% of decisions unchanged,
- and the customer has signed off on the rule values.

**No-go if** any uncertain or missing field can reach auto-approval, any decision can't be traced to evidence and reasoning, or operators override more than a third of decisions for reasons we can't fix within the pilot. These thresholds are my proposal and should be agreed with the customer before the pilot starts.

---

## 8. What's next

Two more weeks, in this order:

1. **Real documents with customer-checked labels**, including handwriting, scans, and known-bad cases. Everything I've measured so far is synthetic, so this comes first.
2. **A working OCR path for image-only documents**, then rerun every eval on the local models.
3. **Email trigger and cross-document checks.** In real life a shipment arrives as several documents, and the consignee and HS code have to agree across all of them. This is where most of the value is for CG.
4. **A supervised pilot** that records every operator override, which then becomes the best test data I'll have.

I'm putting data and OCR ahead of interface polish because a nicer screen on top of an unproven benchmark doesn't reduce risk. I'd leave retrieval over long documents and multi-customer scaling for later, since they only matter once one rule file and one customer stop being enough.
