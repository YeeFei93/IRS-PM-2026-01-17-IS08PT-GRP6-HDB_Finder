from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from html import escape
from statistics import mean
from typing import Any


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(_THIS_DIR, "results.csv")
SUBMISSION_LOG = os.path.join(_THIS_DIR, "submission_rounds.jsonl")
DEFAULT_HTML_OUTPUT = os.path.join(_THIS_DIR, "evaluation_summary.html")
NDCG_K = 10
PRECISION_K = 10
PRECISION_LABEL = f"Precision@{PRECISION_K}"

CURRENT_MODELS = {
    "cosine_similarity",
    "euclidean_distance",
    "weighted_cosine",
    "knn_cosine_recommender",
}
LEGACY_MODEL_ALIASES = {
    "Cosine Similarity": "cosine_similarity",
    "Weighted Cosine Similarity": "weighted_cosine",
    "kNN Recommender": "euclidean_distance",
}

BUYER_COLUMNS = [
    "cit",
    "age",
    "marital",
    "income",
    "ftimer",
    "prox",
    "ftype",
    "regions",
    "floor",
    "min_lease",
    "cash",
    "cpf",
    "loan",
    "must_have",
]

FLAT_COLUMNS = [
    "rank",
    "score",
    "estate",
    "block",
    "street_name",
    "address",
    "flat_type",
    "flat_model",
    "resale_price",
    "floor_area_sqm",
    "floor_label",
    "remaining_lease_years",
    "remaining_lease_months",
    "remaining_lease_label",
    "sold_date",
    "mrt_count",
    "hawker_count",
    "mall_count",
    "park_count",
    "school_count",
    "hospital_count",
]

CSV_COLUMNS = BUYER_COLUMNS + FLAT_COLUMNS + ["recommendation_model", "relevant"]
LEGACY_CURRENT_CSV_COLUMNS = BUYER_COLUMNS + [
    "rank",
    "score",
    "flat_id",
    "estate",
    "block",
    "street_name",
    "address",
    "flat_type",
    "flat_model",
    "resale_price",
    "floor_area_sqm",
    "floor_label",
    "remaining_lease_years",
    "remaining_lease_months",
    "remaining_lease_label",
    "sold_date",
    "mrt_count",
    "hawker_count",
    "mall_count",
    "park_count",
    "school_count",
    "hospital_count",
] + ["recommendation_model", "relevant"]


def _normalise_model_name(name: str) -> str:
    clean = str(name or "").strip()
    return LEGACY_MODEL_ALIASES.get(clean, clean)


def _read_results_header(csv_path: str) -> list[str]:
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _rewrite_results_without_flat_id(csv_path: str) -> None:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})


def _results_file_locked_message() -> str:
    return "results.csv is open in another program. Close it and try again."


def _ensure_read_storage_ready(
    csv_path: str = RESULTS_CSV,
    log_path: str = SUBMISSION_LOG,
) -> None:
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(CSV_COLUMNS)
        except PermissionError:
            pass

    if not os.path.exists(log_path):
        try:
            with open(log_path, "a", encoding="utf-8", newline=""):
                pass
        except PermissionError:
            pass


def _ensure_write_storage_ready(
    csv_path: str = RESULTS_CSV,
    log_path: str = SUBMISSION_LOG,
) -> None:
    existing_header = _read_results_header(csv_path)
    if existing_header == LEGACY_CURRENT_CSV_COLUMNS:
        try:
            _rewrite_results_without_flat_id(csv_path)
        except PermissionError as exc:
            raise RuntimeError(_results_file_locked_message()) from exc
        existing_header = CSV_COLUMNS
    elif os.path.exists(csv_path) and os.path.getsize(csv_path) > 0 and existing_header and existing_header != CSV_COLUMNS:
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(CSV_COLUMNS)
        except PermissionError as exc:
            raise RuntimeError(_results_file_locked_message()) from exc
        if os.path.exists(log_path):
            try:
                with open(log_path, "w", encoding="utf-8", newline=""):
                    pass
            except PermissionError as exc:
                raise RuntimeError("submission_rounds.jsonl is open in another program. Close it and try again.") from exc

    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(CSV_COLUMNS)
        except PermissionError as exc:
            raise RuntimeError(_results_file_locked_message()) from exc

    if not os.path.exists(log_path):
        try:
            with open(log_path, "a", encoding="utf-8", newline=""):
                pass
        except PermissionError as exc:
            raise RuntimeError("submission_rounds.jsonl is open in another program. Close it and try again.") from exc

    existing_header = _read_results_header(csv_path)
    if existing_header != CSV_COLUMNS:
        raise RuntimeError("results.csv is using an unsupported format. Close the file and restart the evaluator.")


def _append_submission_log(
    submission_id: str,
    grouped_recommendations: list[dict[str, Any]],
    log_path: str = SUBMISSION_LOG,
) -> None:
    payload = {
        "submission_id": submission_id,
        "model_runs": [
            {
                "model_name": _normalise_model_name(group.get("model_name", "")),
                "count": len(group.get("items", [])),
            }
            for group in grouped_recommendations
        ],
    }
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _serialise_profile_value(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def _flatten_profile(profile: dict[str, Any]) -> dict[str, str]:
    return {column: _serialise_profile_value(profile.get(column, "")) for column in BUYER_COLUMNS}


def _flatten_item(item: dict[str, Any]) -> dict[str, Any]:
    amenity_counts = item.get("amenity_counts") or {}
    return {
        "rank": item.get("rank", ""),
        "score": item.get("score", ""),
        "estate": item.get("estate", ""),
        "block": item.get("block", ""),
        "street_name": item.get("street_name", ""),
        "address": item.get("address", ""),
        "flat_type": item.get("flat_type", ""),
        "flat_model": item.get("flat_model", ""),
        "resale_price": item.get("resale_price", ""),
        "floor_area_sqm": item.get("floor_area_sqm", ""),
        "floor_label": item.get("floor_label", ""),
        "remaining_lease_years": item.get("remaining_lease_years", ""),
        "remaining_lease_months": item.get("remaining_lease_months", ""),
        "remaining_lease_label": item.get("remaining_lease_label", ""),
        "sold_date": item.get("sold_date", ""),
        "mrt_count": amenity_counts.get("mrt", 0),
        "hawker_count": amenity_counts.get("hawker", 0),
        "mall_count": amenity_counts.get("mall", 0),
        "park_count": amenity_counts.get("park", 0),
        "school_count": amenity_counts.get("school", 0),
        "hospital_count": amenity_counts.get("hospital", 0),
    }


def append_feedback(
    submission_id: str,
    profile: dict[str, Any],
    grouped_recommendations: list[dict[str, Any]],
    selected_keys: set[str],
    csv_path: str = RESULTS_CSV,
    log_path: str = SUBMISSION_LOG,
) -> int:
    _ensure_write_storage_ready(csv_path, log_path)
    written = 0
    profile_row = _flatten_profile(profile)

    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)

            for group in grouped_recommendations:
                model_name = _normalise_model_name(group.get("model_name", ""))

                for item in group.get("items", []):
                    row_key = f"{group['model_key']}::{item['flat_id']}"
                    flat_row = _flatten_item(item)
                    writer.writerow(
                        [profile_row[column] for column in BUYER_COLUMNS]
                        + [flat_row[column] for column in FLAT_COLUMNS]
                        + [model_name, "yes" if row_key in selected_keys else "no"]
                    )
                    written += 1
    except PermissionError as exc:
        raise RuntimeError(_results_file_locked_message()) from exc

    _append_submission_log(submission_id, grouped_recommendations, log_path)
    return written


def _load_current_feedback(csv_path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            if not raw_row:
                continue
            rows.append(
                {
                    "model_name": _normalise_model_name(raw_row.get("recommendation_model", "")),
                    "relevant": str(raw_row.get("relevant", "")).strip().lower(),
                    "rank": raw_row.get("rank", ""),
                }
            )
    return rows


def _load_legacy_feedback(csv_path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for raw_row in reader:
            if not raw_row:
                continue
            if raw_row[0] == "submission_id":
                continue
            if len(raw_row) >= 5:
                rows.append(
                    {
                        "model_name": _normalise_model_name(raw_row[3]),
                        "relevant": raw_row[4].strip().lower(),
                        "rank": "",
                    }
                )
            elif len(raw_row) >= 4:
                rows.append(
                    {
                        "model_name": _normalise_model_name(raw_row[2]),
                        "relevant": raw_row[3].strip().lower(),
                        "rank": "",
                    }
                )
    return rows


def load_feedback(csv_path: str = RESULTS_CSV) -> list[dict[str, Any]]:
    _ensure_read_storage_ready(csv_path)
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return []

    header = _read_results_header(csv_path)
    if header in (CSV_COLUMNS, LEGACY_CURRENT_CSV_COLUMNS):
        return _load_current_feedback(csv_path)
    return _load_legacy_feedback(csv_path)


def _load_submission_log(log_path: str = SUBMISSION_LOG) -> list[dict[str, Any]]:
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return []

    sessions: list[dict[str, Any]] = []
    with open(log_path, encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                session = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(session, dict):
                sessions.append(session)
    return sessions


def _assign_rows_without_log(
    rows: list[dict[str, Any]],
    start_index: int = 1,
) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    submission_index = start_index
    seen_models: set[str] = set()
    previous_model = ""

    for row in rows:
        model_name = row.get("model_name", "")
        if previous_model and model_name != previous_model and model_name in seen_models:
            submission_index += 1
            seen_models = set()

        seen_models.add(model_name)
        previous_model = model_name
        assigned.append({**row, "submission_id": f"submission_{submission_index}"})

    return assigned


def load_feedback_with_submissions(
    csv_path: str = RESULTS_CSV,
    log_path: str = SUBMISSION_LOG,
) -> list[dict[str, Any]]:
    rows = load_feedback(csv_path)
    if not rows:
        return []

    sessions = _load_submission_log(log_path)
    if not sessions:
        return _assign_rows_without_log(rows)

    assigned: list[dict[str, Any]] = []
    cursor = 0
    submission_index = 1

    for session in sessions:
        submission_id = str(session.get("submission_id") or f"submission_{submission_index}")
        model_runs = session.get("model_runs") or []

        for run in model_runs:
            try:
                count = max(int(run.get("count", 0)), 0)
            except (TypeError, ValueError):
                count = 0

            chunk = rows[cursor: cursor + count]
            for row in chunk:
                assigned.append({**row, "submission_id": submission_id})
            cursor += count

        submission_index += 1
        if cursor >= len(rows):
            break

    if cursor < len(rows):
        assigned.extend(_assign_rows_without_log(rows[cursor:], start_index=submission_index))

    return assigned


def _precision_at_k(binary_relevance: list[int], k: int = PRECISION_K) -> float:
    top_k = binary_relevance[:k]
    if not top_k:
        return 0.0
    return sum(top_k) / len(top_k)


def _dcg_at_k(binary_relevance: list[int], k: int = NDCG_K) -> float:
    dcg = 0.0
    for idx, relevant in enumerate(binary_relevance[:k], start=1):
        if relevant:
            dcg += 1.0 / math.log2(idx + 1)
    return dcg


def _ndcg_at_k(binary_relevance: list[int], k: int = NDCG_K) -> float:
    dcg = _dcg_at_k(binary_relevance, k)
    ideal = sorted(binary_relevance, reverse=True)
    ideal_dcg = _dcg_at_k(ideal, k)
    if ideal_dcg == 0.0:
        return 0.0
    return dcg / ideal_dcg


def _sort_session_rows(session_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed_rows = list(enumerate(session_rows))

    def _rank_key(pair: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, row = pair
        try:
            rank = int(row.get("rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        return (rank if rank > 0 else 10**6 + index, index)

    return [row for _, row in sorted(indexed_rows, key=_rank_key)]


def calculate_model_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_rows = [row for row in rows if row.get("model_name") in CURRENT_MODELS]
    grouped_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in valid_rows:
        grouped_rows[(row["submission_id"], row["model_name"])].append(row)

    per_model_sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for (submission_id, model_name), session_rows in grouped_rows.items():
        ordered_rows = _sort_session_rows(session_rows)
        relevance = [1 if item.get("relevant") == "yes" else 0 for item in ordered_rows]
        displayed = len(relevance)
        relevant_count = sum(relevance)
        relevant_ranks = [idx for idx, rel in enumerate(relevance, start=1) if rel]

        per_model_sessions[model_name].append(
            {
                "submission_id": submission_id,
                "displayed": displayed,
                "relevant_count": relevant_count,
                "relevance_rate": (relevant_count / displayed) if displayed else 0.0,
                "precision_at_k": _precision_at_k(relevance, PRECISION_K),
                "ndcg_at_10": _ndcg_at_k(relevance, NDCG_K),
                "avg_relevant_rank": mean(relevant_ranks) if relevant_ranks else None,
            }
        )

    metrics: list[dict[str, Any]] = []
    for model_name, sessions in per_model_sessions.items():
        total_displayed = sum(session["displayed"] for session in sessions)
        total_relevant = sum(session["relevant_count"] for session in sessions)
        avg_rank_values = [session["avg_relevant_rank"] for session in sessions if session["avg_relevant_rank"] is not None]

        metrics.append(
            {
                "model_key": model_name,
                "model_name": model_name,
                "sessions": len(sessions),
                "rated_flats": total_displayed,
                "relevant_flats": total_relevant,
                "relevance_rate": (total_relevant / total_displayed) if total_displayed else 0.0,
                "precision_at_k": mean(session["precision_at_k"] for session in sessions),
                "ndcg_at_10": mean(session["ndcg_at_10"] for session in sessions),
                "avg_relevant_rank": mean(avg_rank_values) if avg_rank_values else None,
            }
        )

    metrics.sort(
        key=lambda item: (
            item["ndcg_at_10"],
            item["precision_at_k"],
            item["relevance_rate"],
            item["sessions"],
        ),
        reverse=True,
    )
    return metrics


def build_summary_context(
    csv_path: str = RESULTS_CSV,
    log_path: str = SUBMISSION_LOG,
) -> dict[str, Any]:
    rows = load_feedback_with_submissions(csv_path, log_path)
    filtered_rows = [row for row in rows if row.get("model_name") in CURRENT_MODELS]
    metrics = calculate_model_metrics(filtered_rows)
    submissions = {row["submission_id"] for row in filtered_rows}
    models_compared = len({row["model_name"] for row in filtered_rows})
    return {
        "rows": filtered_rows,
        "metrics": metrics,
        "total_rows": len(filtered_rows),
        "total_submissions": len(submissions),
        "models_compared": models_compared,
        "best_model": metrics[0] if metrics else None,
    }


def _avg_rank_text(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def render_summary_html(
    csv_path: str = RESULTS_CSV,
    log_path: str = SUBMISSION_LOG,
) -> str:
    summary = build_summary_context(csv_path, log_path)
    best_model_html = "<p>No ratings have been collected yet.</p>"
    if summary["best_model"]:
        best_model_html = (
            f"<p><strong>Best Model:</strong> {escape(summary['best_model']['model_name'])}</p>"
        )

    metric_rows = "".join(
        f"""
        <tr>
          <td>{escape(metric['model_name'])}</td>
          <td>{metric['sessions']}</td>
          <td>{metric['relevant_flats']}/{metric['rated_flats']}</td>
          <td>{metric['precision_at_k']:.4f}</td>
          <td>{metric['ndcg_at_10']:.4f}</td>
          <td>{_avg_rank_text(metric['avg_relevant_rank'])}</td>
        </tr>
        """
        for metric in summary["metrics"]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Evaluation Summary</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f8fafc; color: #1f2937; }}
    .panel {{ background: #fff; border: 1px solid #dbe1ea; border-radius: 12px; padding: 20px; max-width: 1100px; }}
    .badge-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }}
    .badge {{ background: #f8fafc; border: 1px solid #dbe1ea; border-radius: 10px; padding: 12px 14px; }}
    .label {{ text-transform: uppercase; letter-spacing: 0.05em; font-size: 11px; color: #64748b; margin-bottom: 4px; }}
    .value {{ font-size: 20px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid #e5e7eb; }}
    th {{ background: #f8fafc; color: #64748b; text-transform: uppercase; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>Current Evaluation Status</h1>
    <div class="badge-grid">
      <div class="badge">
        <div class="label">Collected Ratings</div>
        <div class="value">{summary['total_rows']}</div>
      </div>
      <div class="badge">
        <div class="label">Submission Rounds</div>
        <div class="value">{summary['total_submissions']}</div>
      </div>
      <div class="badge">
        <div class="label">Compared Models</div>
        <div class="value">{summary['models_compared']}</div>
      </div>
    </div>
    <h2>Best Model</h2>
    {best_model_html}
    <h2>Evaluation Summary</h2>
    <table>
      <thead>
        <tr>
          <th>Model</th>
          <th>Sessions</th>
          <th>Relevant Flats</th>
          <th>{escape(PRECISION_LABEL)}</th>
          <th>NDCG@{NDCG_K}</th>
          <th>Average Relevant Rank</th>
        </tr>
      </thead>
      <tbody>
        {metric_rows}
      </tbody>
    </table>
  </div>
</body>
</html>"""


def write_summary_html(
    csv_path: str = RESULTS_CSV,
    output_path: str = DEFAULT_HTML_OUTPUT,
    log_path: str = SUBMISSION_LOG,
) -> str:
    html = render_summary_html(csv_path, log_path)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return output_path


if __name__ == "__main__":
    output = write_summary_html()
    print(f"Wrote evaluation summary to {escape(output)}")
