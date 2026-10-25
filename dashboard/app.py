from __future__ import annotations

import os
from html import escape
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = (3.0, 15.0)

st.set_page_config(page_title="GameMatch · Discover", page_icon="🎮", layout="wide")
st.markdown(
    """
    <style>
      :root { color-scheme: dark; }
      .stApp { background: #080d19; }
      [data-testid="stSidebar"] { background: #0d1424; border-right: 1px solid #202a3c; }
      .block-container { max-width: 1380px; padding-top: 2.1rem; }
      h1, h2, h3 { color: #f4f7ff; letter-spacing: -.02em; }
      .eyebrow { color: #61e5c1; text-transform: uppercase; letter-spacing: .18em; font-size: .72rem; font-weight: 700; }
      .muted { color: #9aa8bf; }
      .game-card { background: linear-gradient(145deg,#121d31,#101827); border: 1px solid #27334a; border-radius: 16px; padding: 1rem 1.1rem; margin: .35rem 0 .8rem; min-height: 150px; }
      .game-title { color: #f5f7ff; font-size: 1.1rem; font-weight: 700; margin-bottom: .35rem; }
      .game-meta { color: #9faec4; font-size: .84rem; }
      .game-explanation { color: #d6e2f5; margin-top: .65rem; font-size: .9rem; }
      div[data-testid="stMetric"] { background:#101827; border:1px solid #27334a; padding:1rem; border-radius:14px; }
      .stButton button[kind="primary"] { background:#35c9a4; color:#071119; border:0; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"GameMatch API is unavailable at {API_BASE}: {exc}")
        return None


def api_post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.post(f"{API_BASE}{path}", json=body, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"Request could not be completed: {exc}")
        return None


def api_put(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.put(f"{API_BASE}{path}", json=body, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"Request could not be completed: {exc}")
        return None


def heading(section: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="eyebrow">{section}</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(subtitle)


def game_card(game: dict[str, Any], *, explanation: str | None = None, score: float | None = None, feedback: bool = False) -> None:
    genres = escape(", ".join(game.get("genres", [])[:4]) or "Genre metadata unavailable")
    score_text = f" · rank score {score:.3f}" if score is not None else ""
    reason = f'<div class="game-explanation">{escape(explanation)}</div>' if explanation else ""
    st.markdown(
        f'<div class="game-card"><div class="game-title">{escape(str(game.get("title", "Untitled game")))}</div>'
        f'<div class="game-meta">Steam app {escape(str(game.get("id", "—")))} · {genres}{score_text}</div>{reason}</div>',
        unsafe_allow_html=True,
    )
    if feedback and st.session_state.get("user_id"):
        columns = st.columns(3)
        for column, value, label in zip(columns, ("useful", "not_relevant", "already_played"), ("Useful", "Not relevant", "Already played")):
            with column:
                if st.button(label, key=f"{game.get('id')}-{value}"):
                    api_post("/v1/feedback", {"user_id": st.session_state.user_id, "game_id": str(game["id"]), "value": value})
                    st.toast("Feedback saved for later analysis.")


def load_model() -> dict[str, Any] | None:
    return api_get("/v1/model/info")


with st.sidebar:
    st.markdown("# 🎮 GameMatch")
    st.caption("A more thoughtful way to find your next game.")
    page = st.radio("Workspace", ["Discover", "For You", "Similar Games", "Model Evaluation", "Data & Model", "Feedback & Monitoring"], label_visibility="collapsed")
    st.divider()
    st.caption(f"API · {API_BASE}")
    health = api_get("/ready")
    st.markdown("🟢 Ready" if health else "🟠 Waiting for API")

model = load_model()

if page == "Discover":
    heading("Game library", "Find your next favorite", "Search the verified Steam sample catalog and see the popularity signal used by the baseline.")
    query_col, genre_col = st.columns([3, 1])
    with query_col:
        query = st.text_input("Search games", placeholder="Try Portal, Stardew Valley, or Hades")
    with genre_col:
        genre = st.text_input("Genre filter", placeholder="Action")
    params: dict[str, Any] = {"limit": 24}
    if query:
        params["search"] = query
    if genre:
        params["genre"] = genre
    catalog = api_get("/v1/games", params)
    if catalog:
        st.caption(f"Showing {len(catalog['items'])} of {catalog['total']:,} matching games")
        if not catalog["items"]:
            st.info("No games match those filters. Try a broader search.")
        columns = st.columns(3)
        for index, game in enumerate(catalog["items"]):
            with columns[index % 3]:
                game_card(game)
                if st.button("Add to your picks", key=f"pick-{game['id']}"):
                    history = st.session_state.setdefault("game_history", [])
                    if str(game["id"]) not in history:
                        history.append(str(game["id"]))
                    st.toast(f"Added {game['title']} to your picks.")

elif page == "For You":
    heading("Personalized discovery", "Built around what you play", "Choose games you enjoy. GameMatch blends content similarity, co-play patterns, and the measured popularity baseline.")
    identity = st.text_input("Optional profile ID", value=st.session_state.get("user_id", ""), max_chars=128, help="A random nickname works. It is stored as an HMAC hash for saved picks and feedback.")
    if identity:
        st.session_state.user_id = identity
    elif "user_id" in st.session_state:
        del st.session_state.user_id
    search = st.text_input("Find a game to add to your history", key="for-you-search", placeholder="Search title")
    search_results = api_get("/v1/games", {"search": search, "limit": 30}) if search else api_get("/v1/games", {"limit": 30})
    id_by_label: dict[str, str] = {}
    if search_results:
        id_by_label = {f"{game['title']} · {game['id']}": str(game["id"]) for game in search_results["items"]}
    selected_labels = st.multiselect("Games you've played or enjoyed", list(id_by_label))
    history_ids = list(dict.fromkeys(st.session_state.get("game_history", []) + [id_by_label[label] for label in selected_labels]))
    st.caption(f"{len(history_ids)} games in the current recommendation history")
    if st.session_state.get("user_id") and st.button("Save these picks to profile") and history_ids:
        result = api_put(f"/v1/users/{st.session_state.user_id}/interactions", {"positive_game_ids": history_ids})
        if result:
            st.success(f"Saved {result['stored_interactions']} positive interactions.")
    left, right = st.columns([1, 2])
    with left:
        count = st.slider("How many recommendations?", 5, 20, 10)
        preferred_genre = st.text_input("Optional genre", placeholder="RPG")
        get_recs = st.button("Show recommendations", type="primary")
    if get_recs:
        body = {"positive_game_ids": history_ids, "n": count}
        if st.session_state.get("user_id"):
            body["user_id"] = st.session_state.user_id
        if preferred_genre:
            body["genre"] = preferred_genre
        payload = api_post("/v1/recommendations", body)
        if payload:
            mode = "Personalized" if payload["fallback_mode"] == "personalized" else "Popularity fallback"
            st.success(f"{mode} · model {payload['model_version']}")
            if not history_ids and not st.session_state.get("user_id"):
                st.info("Add a few games above to get recommendations based on their attributes and co-play patterns.")
            for row in payload["recommendations"]:
                game_card({"id": row["game_id"], "title": row["title"], "genres": row["genres"]}, explanation=row["explanation"], score=row["score"], feedback=bool(st.session_state.get("user_id")))
    elif model:
        with right:
            st.metric("Catalog games", f"{model['n_games']:,}")
            st.caption("Recommendations use historical playtime, game metadata, and training-only popularity. Scores are ranking signals, not probabilities.")

elif page == "Similar Games":
    heading("Game-to-game discovery", "Explore games with shared DNA", "Content similarity uses observed genres, tags, and specifications. Collaborative similarity uses library co-occurrence.")
    search = st.text_input("Search for a starting game", placeholder="Portal 2")
    matches = api_get("/v1/games", {"search": search, "limit": 30}) if search else api_get("/v1/games", {"limit": 30})
    game_ids = {f"{row['title']} · {row['id']}": str(row["id"]) for row in matches["items"]} if matches else {}
    if game_ids:
        label = st.selectbox("Starting game", list(game_ids))
        similarity_method = st.radio("Similarity evidence", ["content", "collaborative"], horizontal=True)
        if st.button("Explore similar games", type="primary"):
            result = api_get(f"/v1/games/{game_ids[label]}/similar", {"model": similarity_method, "n": 12})
            if result:
                if not result["recommendations"]:
                    st.info("No games with enough matching interaction or metadata are available for this selection.")
                for row in result["recommendations"]:
                    game_card({"id": row["game_id"], "title": row["title"], "genres": row["genres"]}, explanation=row["explanation"], score=row["score"])

elif page == "Model Evaluation":
    heading("Offline experiment", "How the models compare", "All numbers below come from one reproducible held-out test split. Validation selected the hybrid weights; the test split did not.")
    if model:
        metrics = model.get("offline_test_metrics", {})
        names = [name for name in ("popularity", "content", "collaborative", "hybrid") if name in metrics]
        if names:
            metric_name = st.selectbox("Ranking metric", ["ndcg@10", "precision@5", "recall@10", "map@10"])
            frame = pd.DataFrame({"Model": names, metric_name: [metrics[name].get(metric_name, 0.0) for name in names]})
            st.plotly_chart(px.bar(frame, x="Model", y=metric_name, color="Model", template="plotly_dark", title=metric_name.upper()), use_container_width=True)
            st.dataframe(pd.DataFrame({"Model": names, **{key: [metrics[name].get(key) for name in names] for key in ("precision@5", "recall@10", "ndcg@10", "map@10", "catalog_coverage_at_10", "intra_list_diversity@10", "novelty_bits@10", "top_decile_popularity_share@10")}}), hide_index=True, use_container_width=True)
            ci = metrics.get("hybrid", {}).get("ndcg@10_user_bootstrap_95ci", {})
            if ci:
                st.caption(f"Hybrid NDCG@10 user bootstrap 95% interval: {ci.get('lower_95', 0):.4f}–{ci.get('upper_95', 0):.4f}. This varies users within the split; it does not estimate time or split variation.")
            st.subheader("History-length groups")
            groups = metrics.get("hybrid", {}).get("history_groups", {})
            if groups:
                st.dataframe(pd.DataFrame([{"Training history": label, **summary} for label, summary in groups.items()]), hide_index=True, use_container_width=True)
            else:
                st.info("History-group results are unavailable in this artifact.")
        else:
            st.info("No completed offline evaluation is present in the loaded model artifact.")
    else:
        st.info("The API has not loaded a trained model artifact yet.")

elif page == "Data & Model":
    heading("Provenance", "Know what this model learned", "Dataset, target construction, model version, and limitations are kept visible alongside recommendations.")
    if model:
        left, right, third = st.columns(3)
        left.metric("Training users", f"{model['n_users']:,}")
        right.metric("Training interactions", f"{model['n_train_interactions']:,}")
        third.metric("Candidate games", f"{model['candidate_games']:,}")
        st.json(model)
    st.markdown("**Source:** [UCSD/McAuley Steam Video Game and Bundle Data](https://cseweb.ucsd.edu/~jmcauley/datasets.html#steam_data). The Australian library snapshot records playtime but no reliable interaction timestamps. The dataset page requests citation and lists academic references; it does not state a formal reuse license.")
    st.markdown("**Target:** games with positive recorded playtime, excluding explicit `recommend = false` review pairs. Zero-playtime ownership and unobserved games are unknown, not negative feedback.")
    st.markdown("**Caveat:** this historical regional sample is a demonstration corpus. Offline rank metrics do not prove satisfaction, purchases, engagement, or retention.")

else:
    heading("Measured operations", "Production traffic and feedback", "Offline ranking results and live request measurements are shown separately. Feedback remains a review signal; it never retrains the model automatically.")
    metrics = api_get("/v1/metrics/summary")
    if metrics:
        production = metrics["production"]
        cols = st.columns(4)
        cols[0].metric("API requests · 24h", production["requests"])
        cols[1].metric("5xx errors", production["server_errors"])
        cols[2].metric("P50 latency", f"{production['latency_ms_p50']:.1f} ms" if production["latency_ms_p50"] is not None else "No traffic yet")
        cols[3].metric("P95 latency", f"{production['latency_ms_p95']:.1f} ms" if production["latency_ms_p95"] is not None else "No traffic yet")
        st.subheader("Feedback counts · 24h")
        if production["feedback_counts"]:
            st.bar_chart(pd.DataFrame.from_dict(production["feedback_counts"], orient="index", columns=["Count"]))
        else:
            st.info("No feedback has been recorded in this window.")
        st.subheader("Offline test results")
        offline = metrics.get("offline_evaluation", {})
        if offline:
            st.dataframe(pd.DataFrame([{"Model": name, **summary} for name, summary in offline.items() if isinstance(summary, dict)]), hide_index=True, use_container_width=True)
        else:
            st.info("Offline metrics are unavailable.")
        st.caption("Operational values are measured from this API database. On hosts with ephemeral storage, requests/feedback can be lost across deploys; configure persistent PostgreSQL to retain them.")
