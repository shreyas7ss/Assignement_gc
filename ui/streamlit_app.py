from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st


st.set_page_config(page_title="Nova | Trade docs", layout="wide")


def _api_request(
    url: str,
    *,
    method: str,
    body: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, dict[str, object]]:
    request = Request(
        url,
        data=body,
        method=method,
        headers={"content-type": content_type},
    )
    try:
        with urlopen(request, timeout=180) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        try:
            payload = json.loads(error.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"detail": str(error)}
        return error.code, payload
    except (URLError, TimeoutError) as error:
        return 0, {"detail": str(error)}


st.title("Trade-document review")

with st.sidebar:
    st.subheader("Connection")
    api_url = st.text_input("API URL", value="http://127.0.0.1:8000").rstrip("/")
    if st.button("Check connection", icon=":material/lan:"):
        status, payload = _api_request(f"{api_url}/health", method="GET")
        if status == 200:
            st.success("API connected")
        else:
            st.error(payload.get("detail", "API is unavailable"))

st.subheader("Process document")
uploaded_file = st.file_uploader(
    "Choose a PDF or image",
    type=["pdf", "png", "jpg", "jpeg", "gif", "webp"],
)
if st.button("Run review", type="primary", disabled=uploaded_file is None):
    if uploaded_file is not None:
        query = urlencode({"filename": uploaded_file.name})
        status, payload = _api_request(
            f"{api_url}/runs?{query}",
            method="POST",
            body=uploaded_file.getvalue(),
            content_type=uploaded_file.type or "application/octet-stream",
        )
        if status == 200:
            st.session_state["last_run"] = payload
        else:
            detail = payload.get("detail", "The review could not be completed.")
            if isinstance(detail, dict):
                error = str(detail.get("error", "The review could not be completed."))
                if status == 404 or "model not found" in error.casefold():
                    st.error("The configured Ollama model is not installed. Check `ollama list` or pull the model named in `app/.env`.")
                    st.caption(error)
                elif status == 503 or "cannot reach ollama" in error.casefold():
                    st.error("Ollama is unavailable. Start the local Ollama app and try again.")
                    st.caption(error)
                else:
                    st.error(error)
                shipment_id = detail.get("shipment_id")
                if shipment_id:
                    st.caption(f"Shipment ID: {shipment_id}")
            else:
                st.error(str(detail))

run = st.session_state.get("last_run")
if run:
    decision = run["decision"]
    st.divider()
    st.subheader("Decision")
    metric_columns = st.columns(3)
    metric_columns[0].metric("Outcome", decision["outcome"].replace("_", " ").title())
    metric_columns[1].metric("Shipment", run["shipment_id"][:12])
    metric_columns[2].metric("Document", run["document_name"])
    st.write(decision["reasoning"])

    if decision["amendment_draft"]:
        st.markdown("**Amendment draft**")
        st.dataframe(decision["amendment_draft"], hide_index=True, use_container_width=True)

    st.subheader("Extracted fields")
    st.dataframe(
        [
            {
                "Field": field["field"].replace("_", " ").title(),
                "Value": field["value"],
                "Confidence": field["confidence"],
                "Validation": field["status"].replace("_", " ").title(),
                "Expected": field["expected"],
                "Source quote": field["source_quote"],
                "Page": field["page"],
            }
            for field in run["fields"]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={"Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1)},
    )

st.divider()
st.subheader("Ask the database")
with st.form("database_question"):
    question = st.text_input("Question", placeholder="How many shipments need review?")
    submitted = st.form_submit_button("Run query", icon=":material/search:")

if submitted and question.strip():
    status, payload = _api_request(
        f"{api_url}/queries",
        method="POST",
        body=json.dumps({"question": question}).encode("utf-8"),
    )
    if status == 200:
        st.session_state["last_query"] = payload
    else:
        st.error(payload.get("detail", "The query could not be completed."))

query_result = st.session_state.get("last_query")
if query_result:
    st.code(query_result["sql"], language="sql")
    st.dataframe(query_result["rows"], hide_index=True, use_container_width=True)