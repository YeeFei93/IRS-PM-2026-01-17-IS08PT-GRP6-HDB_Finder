from __future__ import annotations

import json
from html import escape
from typing import Any
from urllib.parse import parse_qs
from uuid import uuid4
from wsgiref.simple_server import make_server

from cosine_similarity import MODEL_KEY as COSINE_KEY, MODEL_NAME as COSINE_NAME, recommend as recommend_cosine
from euclidean_distance_recommender import (
    MODEL_KEY as EUCLIDEAN_KEY,
    MODEL_NAME as EUCLIDEAN_NAME,
    recommend as recommend_euclidean,
)
from evaluate_recommender import NDCG_K, PRECISION_LABEL, append_feedback, build_summary_context
from input_data_for_all_models import (
    AMENITY_OPTIONS,
    CITIZENSHIP_OPTIONS,
    DEFAULT_PROFILE,
    FLAT_TYPE_OPTIONS,
    FLOOR_OPTIONS,
    FTIMER_OPTIONS,
    MARITAL_OPTIONS,
    PROX_OPTIONS,
    REGION_OPTIONS,
    attach_display_amenities,
    build_model_context,
    evaluate_profile_eligibility,
    ftimer_options_for_cit,
    marital_options_for_cit,
    parse_profile_form,
    profile_from_json,
    profile_to_json,
)
from knn_recommender import MODEL_KEY as KNN_KEY, MODEL_NAME as KNN_NAME, recommend as recommend_knn
from weighted_cosine_similarity import (
    MODEL_KEY as WEIGHTED_KEY,
    MODEL_NAME as WEIGHTED_NAME,
    recommend as recommend_weighted,
)


APP_TITLE = "AI Recommender Evaluator"
HOST = "127.0.0.1"
PORT = 8011

MODEL_RUNNERS = [
    (COSINE_KEY, COSINE_NAME, recommend_cosine),
    (EUCLIDEAN_KEY, EUCLIDEAN_NAME, recommend_euclidean),
    (WEIGHTED_KEY, WEIGHTED_NAME, recommend_weighted),
    (KNN_KEY, KNN_NAME, recommend_knn),
]


def _empty_summary_context() -> dict[str, Any]:
    return {
        "rows": [],
        "metrics": [],
        "total_rows": 0,
        "total_submissions": 0,
        "models_compared": 0,
        "best_model": None,
    }


def _safe_build_summary_context() -> dict[str, Any]:
    try:
        return build_summary_context()
    except Exception:
        return _empty_summary_context()


def _money(value: float) -> str:
    return f"${int(round(value)):,}"


def _selected(current: str, expected: str) -> str:
    return " selected" if current == expected else ""


def _checked(values: list[str], expected: str) -> str:
    return " checked" if expected in values else ""


def _clone_profile(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {
        **DEFAULT_PROFILE,
        "regions": list(DEFAULT_PROFILE["regions"]),
        "must_have": list(DEFAULT_PROFILE["must_have"]),
    }
    if profile:
        base.update(profile)
        base["regions"] = list(profile.get("regions", []))
        base["must_have"] = list(profile.get("must_have", []))
    return base


def _read_form_data(environ: dict[str, Any]) -> dict[str, list[str]]:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    raw = environ["wsgi.input"].read(length).decode("utf-8")
    return parse_qs(raw, keep_blank_values=True)


def _html_page(title: str, sidebar: str, content: str) -> bytes:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #eef2f6;
      color: #1f2937;
    }}
    .page {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 20px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(320px, 360px) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }}
    .sidebar {{
      position: sticky;
      top: 20px;
    }}
    .panel {{
      background: #ffffff;
      border: 1px solid #dbe1ea;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
      margin-bottom: 18px;
    }}
    h1, h2, h3 {{
      margin-top: 0;
    }}
    h2 {{
      font-size: 20px;
      margin-bottom: 10px;
    }}
    h3 {{
      font-size: 18px;
      margin-bottom: 8px;
    }}
    .muted {{
      color: #64748b;
      font-size: 13px;
    }}
    .field {{
      margin-bottom: 14px;
    }}
    label {{
      display: block;
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 6px;
      color: #475569;
    }}
    input[type="number"], select {{
      width: 100%;
      box-sizing: border-box;
      padding: 10px 12px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #ffffff;
      font-size: 14px;
    }}
    .checkbox-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 12px;
      padding-top: 2px;
    }}
    .checkbox-grid label {{
      font-weight: 500;
      margin-bottom: 0;
    }}
    .button-row {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
      margin-top: 14px;
    }}
    button {{
      border: 0;
      border-radius: 8px;
      background: #2563eb;
      color: #ffffff;
      padding: 11px 14px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{
      background: #475569;
    }}
    .badge-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .badge {{
      background: #f8fafc;
      border: 1px solid #dbe1ea;
      border-radius: 10px;
      padding: 12px 14px;
    }}
    .badge .label {{
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: 11px;
      color: #64748b;
      margin-bottom: 4px;
    }}
    .badge .value {{
      font-size: 20px;
      font-weight: 700;
    }}
    .notice {{
      padding: 12px 14px;
      border-radius: 10px;
      line-height: 1.6;
      margin-top: 12px;
    }}
    .notice.ok {{
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
    }}
    .notice.warn {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
    }}
    .notice.info {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
    }}
    .note-list {{
      margin: 10px 0 0;
      padding-left: 18px;
    }}
    .section-stack > * {{
      margin-bottom: 18px;
    }}
    .section-stack > *:last-child {{
      margin-bottom: 0;
    }}
    .model-card {{
      margin-top: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      background: #ffffff;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #e5e7eb;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #f8fafc;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: 12px;
      position: sticky;
      top: 0;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    .best-model {{
      background: #f8fff5;
    }}
    code {{
      background: #eef2ff;
      padding: 2px 6px;
      border-radius: 6px;
    }}
    @media (max-width: 1080px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="layout">
      <aside class="sidebar">{sidebar}</aside>
      <main>{content}</main>
    </div>
  </div>
</body>
</html>"""
    return html.encode("utf-8")


def _sidebar_panel(profile: dict[str, Any], summary_context: dict[str, Any], eligibility: dict[str, Any]) -> str:
    visible_marital = {item["value"] for item in marital_options_for_cit(profile["cit"])}
    visible_ftimer = {item["value"] for item in ftimer_options_for_cit(profile["cit"])}
    notice_class = "ok" if eligibility.get("eligible") else "warn"
    notice_heading = "Eligible to run recommendations." if eligibility.get("eligible") else "Resolve eligibility issues before running recommendations."
    notice_parts: list[str] = []
    if eligibility.get("warnings"):
        notice_parts.append("<ul class='note-list'>{}</ul>".format("".join(f"<li>{escape(item)}</li>" for item in eligibility["warnings"])))
    if eligibility.get("notes"):
        notice_parts.append("<ul class='note-list'>{}</ul>".format("".join(f"<li>{escape(item)}</li>" for item in eligibility["notes"])))
    notice_html = "".join(notice_parts)

    return f"""
    <div class="panel">
      <!--<div class="notice {notice_class}">-->
        <!--<strong>{escape(notice_heading)}</strong>-->
        <!--{notice_html}-->
      <!--</div>-->
      <form method="post" action="/">
        <div class="field">
          <label>Citizenship Status</label>
          <select id="cit-select" name="cit">
            {"".join(f"<option value='{escape(value)}'{_selected(profile['cit'], value)}>{escape(label)}</option>" for value, label in CITIZENSHIP_OPTIONS)}
          </select>
        </div>

        <div class="field">
          <label>Marital / Family Status</label>
          <select id="marital-select" name="marital">
            {"".join(
                f"<option value='{escape(item['value'])}' data-groups='{escape(','.join(item['groups']))}'"
                f"{_selected(profile['marital'], item['value'])}"
                f"{'' if item['value'] in visible_marital else ' hidden disabled'}>"
                f"{escape(item['label'])}</option>"
                for item in MARITAL_OPTIONS
            )}
          </select>
        </div>

        <div class="field">
          <label>First-Timer Status</label>
          <select id="ftimer-select" name="ftimer">
            {"".join(
                f"<option value='{escape(item['value'])}' data-groups='{escape(','.join(item['groups']))}'"
                f"{_selected(profile['ftimer'], item['value'])}"
                f"{'' if item['value'] in visible_ftimer else ' hidden disabled'}>"
                f"{escape(item['label'])}</option>"
                for item in FTIMER_OPTIONS
            )}
          </select>
        </div>

        <div class="field">
          <label>Living Near / With Parents?</label>
          <select name="prox">
            {"".join(f"<option value='{escape(value)}'{_selected(profile['prox'], value)}>{escape(label)}</option>" for value, label in PROX_OPTIONS)}
          </select>
        </div>

        <div class="field">
          <label>Age - Youngest Applicant</label>
          <input type="number" name="age" min="21" max="70" step="1" value="{profile['age']}">
        </div>

        <div class="field">
          <label>Monthly Household Income ($)</label>
          <input type="number" name="income" min="0" max="21000" step="500" value="{profile['income']}">
        </div>

        <div class="field">
          <label>Flat Type</label>
          <select name="ftype">
            {"".join(f"<option value='{escape(value)}'{_selected(profile['ftype'], value)}>{escape(label)}</option>" for value, label in FLAT_TYPE_OPTIONS)}
          </select>
        </div>

        <div class="field">
          <label>Floor Preference</label>
          <select name="floor">
            {"".join(f"<option value='{escape(value)}'{_selected(profile['floor'], value)}>{escape(label)}</option>" for value, label in FLOOR_OPTIONS)}
          </select>
        </div>

        <div class="field">
          <label>Minimum Remaining Lease</label>
          <input type="number" name="min_lease" min="20" max="99" step="5" value="{profile['min_lease']}">
        </div>

        <div class="field">
          <label>Cash Available ($)</label>
          <input type="number" name="cash" min="0" max="500000" step="5000" value="{profile['cash']}">
        </div>

        <div class="field">
          <label>CPF Ordinary Account ($)</label>
          <input type="number" name="cpf" min="0" max="600000" step="5000" value="{profile['cpf']}">
        </div>

        <div class="field">
          <label>Max Monthly Loan Repayment ($)</label>
          <input type="number" name="loan" min="500" max="6000" step="100" value="{profile['loan']}">
        </div>

        <div class="field">
          <label>Preferred Region</label>
          <div class="checkbox-grid">
            {"".join(f"<label><input type='checkbox' name='regions' value='{escape(value)}'{_checked(profile['regions'], value)}> {escape(label)}</label>" for value, label in REGION_OPTIONS)}
          </div>
        </div>

        <div class="field">
          <label>Must-Have Amenities</label>
          <div class="checkbox-grid">
            {"".join(f"<label><input type='checkbox' name='must_have' value='{escape(value)}'{_checked(profile['must_have'], value)}> {escape(label)}</label>" for value, label in AMENITY_OPTIONS)}
          </div>
        </div>

        <div class="button-row">
          <button id="generate-button" type="submit" name="action" value="generate" title="Only eligible buyers can get recommendations.">Get Recommendations</button>
          <button type="submit" name="action" value="evaluate" class="secondary">Show Evaluation Status</button>
        </div>
      </form>

      <script>
        (function() {{
          const form = document.querySelector(".sidebar form");
          const citSelect = document.getElementById("cit-select");
          const maritalSelect = document.getElementById("marital-select");
          const ftimerSelect = document.getElementById("ftimer-select");
          const ageInput = document.querySelector("input[name='age']");
          const generateButton = document.getElementById("generate-button");

          function syncSelect(select) {{
            const currentCit = citSelect.value;
            let firstVisible = null;

            Array.from(select.options).forEach((option) => {{
              const groups = (option.dataset.groups || "").split(",").filter(Boolean);
              const visible = groups.length === 0 || groups.includes(currentCit);
              option.hidden = !visible;
              option.disabled = !visible;
              if (visible && firstVisible === null) {{
                firstVisible = option.value;
              }}
            }});

            const selected = select.options[select.selectedIndex];
            if (!selected || selected.disabled) {{
              select.value = firstVisible || "";
            }}
          }}

          function syncBuyerOptions() {{
            syncSelect(maritalSelect);
            syncSelect(ftimerSelect);
          }}

          function isEligible() {{
            const cit = citSelect.value;
            const marital = maritalSelect.value;
            const age = Number(ageInput.value || 0);
            let eligible = true;

            if (cit === "PR_PR" && marital === "single") {{
              eligible = false;
            }}
            if (cit === "SC_single" && age < 35) {{
              eligible = false;
            }}

            generateButton.title = eligible
              ? "Get recommendations for this buyer profile."
              : "Only eligible buyers can get recommendations.";
            return eligible;
          }}

          function updateEligibilityState() {{
            const eligible = isEligible();
            generateButton.dataset.eligible = eligible ? "true" : "false";
          }}

          form.addEventListener("submit", function(event) {{
            if (event.submitter && event.submitter.value === "generate" && !isEligible()) {{
              event.preventDefault();
              alert("Not eligible.");
            }}
          }});

          citSelect.addEventListener("change", syncBuyerOptions);
          citSelect.addEventListener("change", updateEligibilityState);
          maritalSelect.addEventListener("change", updateEligibilityState);
          ftimerSelect.addEventListener("change", updateEligibilityState);
          ageInput.addEventListener("input", updateEligibilityState);
          syncBuyerOptions();
          updateEligibilityState();
        }})();
      </script>
    </div>
    """


def _render_alert(message: str, kind: str = "info") -> str:
    return f"<div class='panel'><div class='notice {kind}'>{escape(message)}</div></div>"


def _summary_panel(context) -> str:
    warnings = context.eligibility.get("warnings", [])
    notes = context.eligibility.get("notes", []) + context.notes
    notice_class = "ok" if context.eligibility.get("eligible") else "warn"
    headline = (
        "Eligible to generate recommendations."
        if context.eligibility.get("eligible")
        else "Profile is not eligible, so recommendations were not generated."
    )

    warning_html = ""
    if warnings:
        warning_html = "<ul class='note-list'>{}</ul>".format("".join(f"<li>{escape(item)}</li>" for item in warnings))

    note_html = ""
    if notes:
        note_html = "<ul class='note-list'>{}</ul>".format("".join(f"<li>{escape(item)}</li>" for item in notes))

    return f"""
    <div class="panel">
      <div class="badge-grid">
        <div class="badge">
          <div class="label">Effective Budget</div>
          <div class="value">{_money(context.effective_budget)}</div>
        </div>
        <div class="badge">
          <div class="label">Candidate Estates</div>
          <div class="value">{len(context.estate_candidates)}</div>
        </div>
        <div class="badge">
          <div class="label">Candidate Flats</div>
          <div class="value">{len(context.flat_candidates)}</div>
        </div>
        <div class="badge">
          <div class="label">Active Criteria</div>
          <div class="value">{len(context.active_criteria)}</div>
        </div>
      </div>
      <div class="notice {notice_class}">
        <strong>{escape(headline)}</strong>
        {warning_html}
        {note_html}
      </div>
      <div class="muted" style="margin-top: 12px;">
        Grants: EHG {_money(context.grants.get('ehg', 0))}, CPF Grant {_money(context.grants.get('cpf_grant', 0))}, PHG {_money(context.grants.get('phg', 0))}
      </div>
    </div>
    """


def _render_intro_panel(summary_context: dict[str, Any]) -> str:
    return f"""
    <div class="section-stack">
      <div class="panel">
        <div class="notice info">Ratings are collected after submitting relevance ticks and the evaluation status shows the current collection counts.</div>
      </div>
    </div>
    """


def _render_no_results_panel(context) -> str:
    if not context.eligibility.get("eligible"):
        reason = "The profile is currently ineligible."
    elif not context.estate_candidates:
        reason = "No estates passed the current budget, lease, region, and amenity filters."
    else:
        reason = "Estates were found, but no recent flat transactions matched the remaining flat-level filters."

    note_html = ""
    if context.notes:
        note_html = "<ul class='note-list'>{}</ul>".format("".join(f"<li>{escape(item)}</li>" for item in context.notes))

    return f"""
    <div class="panel">
      <h2>No Results Available</h2>
      <p class="muted">{escape(reason)}</p>
      {note_html}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Debug Check</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Eligible</td><td>{escape(str(context.eligibility.get('eligible')))}</td></tr>
            <tr><td>Estate Candidates</td><td>{len(context.estate_candidates)}</td></tr>
            <tr><td>Flat Candidates</td><td>{len(context.flat_candidates)}</td></tr>
            <tr><td>Effective Budget</td><td>{_money(context.effective_budget)}</td></tr>
            <tr><td>Flat Type</td><td>{escape(context.profile.get('ftype', ''))}</td></tr>
            <tr><td>Regions</td><td>{escape(', '.join(context.profile.get('regions', [])) or 'All')}</td></tr>
            <tr><td>Floor Preference</td><td>{escape(context.profile.get('floor', ''))}</td></tr>
            <tr><td>Minimum Lease</td><td>{escape(str(context.profile.get('min_lease', '')))}</td></tr>
            <tr><td>Must-Have Amenities</td><td>{escape(', '.join(context.profile.get('must_have', [])) or 'None')}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    """


def _render_model_tables(grouped_results: list[dict[str, Any]]) -> str:
    model_sections: list[str] = []

    for group in grouped_results:
        rows = []
        for item in group["items"]:
            checkbox_key = f"{group['model_key']}::{item['flat_id']}"
            rows.append(
                f"""
                <tr>
                  <td>{item['rank']}</td>
                  <td><input type="checkbox" name="selected_keys" value="{escape(checkbox_key)}"></td>
                  <td>
                    <strong>{escape(item['estate'])}</strong><br>
                    <span class="muted">{escape(item['address'])}</span>
                  </td>
                  <td>{escape(item['flat_type'])}</td>
                  <td>{_money(item['resale_price'])}</td>
                  <td>{escape(item['floor_label'])}</td>
                  <td>{escape(item.get('remaining_lease_label', f"{item['remaining_lease_years']}y"))}</td>
                  <td>{item['score_pct']:.2f}</td>
                  <td class="muted">{escape(item['amenity_summary'])}</td>
                </tr>
                """
            )

        model_sections.append(
            f"""
            <div class="panel model-card">
              <h3>{escape(group['model_name'])}</h3>
              <div class="muted">Top 10 flats requested. Showing {len(group['items'])} flats returned by this model.</div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Relevant</th>
                      <th>Flat</th>
                      <th>Type</th>
                      <th>Price</th>
                      <th>Floor</th>
                      <th>Lease</th>
                      <th>Score</th>
                      <th>Nearby Amenities</th>
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(rows)}
                  </tbody>
                </table>
              </div>
            </div>
            """
        )

    return "".join(model_sections)


def _render_results_panel(context, grouped_results: list[dict[str, Any]], submission_id: str) -> str:
    payload = json.dumps(grouped_results, separators=(",", ":"))
    profile_json = profile_to_json(context.profile)

    return f"""
    <div class="section-stack">
      {_summary_panel(context)}
      <form method="post" action="/">
        <input type="hidden" name="action" value="submit_ratings">
        <input type="hidden" name="submission_id" value="{escape(submission_id)}">
        <textarea name="profile_json" hidden>{escape(profile_json)}</textarea>
        <textarea name="recommendation_payload" hidden>{escape(payload)}</textarea>
        <div class="panel">
          <h2>Recommendation Outputs And Ranking</h2>
          <p class="muted">
            Tick every flat you think is relevant, then submit once to save feedback into <code>results.csv</code>.
          </p>
          <div class="button-row">
            <button type="submit">Submit Ratings</button>
          </div>
        </div>
        {_render_model_tables(grouped_results)}
      </form>
    </div>
    """


def _render_evaluation_panel(summary_context: dict[str, Any]) -> str:
    best_model_html = "<div class='muted'>No ratings collected yet.</div>"
    if summary_context.get("best_model"):
        best_model = summary_context["best_model"]
        best_model_html = f"""
        <div class="notice ok">
          <strong>Best Model: {escape(best_model['model_name'])}</strong><br>
          <span class="muted">{escape(PRECISION_LABEL)} {best_model['precision_at_k']:.4f}, NDCG@{NDCG_K} {best_model['ndcg_at_10']:.4f}</span>
        </div>
        """

    metric_rows = "".join(
        f"""
        <tr{' class="best-model"' if summary_context.get('best_model') and metric['model_name'] == summary_context['best_model']['model_name'] else ''}>
          <td>{escape(metric['model_name'])}</td>
          <td>{metric['sessions']}</td>
          <td>{metric['relevant_flats']}/{metric['rated_flats']}</td>
          <td>{metric['precision_at_k']:.4f}</td>
          <td>{metric['ndcg_at_10']:.4f}</td>
          <td>{'-' if metric['avg_relevant_rank'] is None else f"{metric['avg_relevant_rank']:.2f}"}</td>
        </tr>
        """
        for metric in summary_context.get("metrics", [])
    )

    return f"""
    <div class="section-stack">
      <div class="panel">
        <h2>Current Evaluation Status</h2>
        <p class="muted">The counts below reflect the feedback collected so far.</p>
        <div class="badge-grid">
          <div class="badge">
            <div class="label">Collected Ratings</div>
            <div class="value">{summary_context['total_rows']}</div>
          </div>
          <div class="badge">
            <div class="label">Submission Rounds</div>
            <div class="value">{summary_context['total_submissions']}</div>
          </div>
          <div class="badge">
            <div class="label">Models Compared</div>
            <div class="value">{summary_context['models_compared']}</div>
          </div>
        </div>
      </div>
      <div class="panel">
        <h2>Best Model</h2>
        {best_model_html}
      </div>
      <div class="panel">
        <h2>Evaluation Summary</h2>
        <div class="table-wrap">
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
      </div>
    </div>
    """


def _run_models(context) -> list[dict[str, Any]]:
    grouped_results: list[dict[str, Any]] = []

    for model_key, model_name, runner in MODEL_RUNNERS:
        items = runner(context, limit=10)
        grouped_results.append(
            {
                "model_key": model_key,
                "model_name": model_name,
                "effective_budget": int(round(context.effective_budget)),
                "buyer_vector": list(context.buyer_vector),
                "items": items,
            }
        )

    attach_display_amenities(grouped_results)
    return grouped_results


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")

    try:
        if path != "/":
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Not Found"]

        if method == "GET":
            summary_context = _safe_build_summary_context()
            profile = _clone_profile()
            sidebar = _sidebar_panel(profile, summary_context, evaluate_profile_eligibility(profile))
            content = _render_intro_panel(summary_context)
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [_html_page(APP_TITLE, sidebar, content)]

        if method == "POST":
            form_data = _read_form_data(environ)
            action = form_data.get("action", ["generate"])[0]
            summary_context = _safe_build_summary_context()

            if action == "submit_ratings":
                submission_id = form_data.get("submission_id", [uuid4().hex])[0]
                profile_json = form_data.get("profile_json", ["{}"])[0]
                payload_json = form_data.get("recommendation_payload", ["[]"])[0]
                selected_keys = set(form_data.get("selected_keys", []))

                profile = profile_from_json(profile_json)
                grouped_results = json.loads(payload_json)
                try:
                    saved_rows = append_feedback(submission_id, profile, grouped_results, selected_keys)
                except RuntimeError as exc:
                    summary_context = _safe_build_summary_context()
                    sidebar = _sidebar_panel(profile, summary_context, evaluate_profile_eligibility(profile))
                    content = _render_alert(str(exc), "warn") + _render_evaluation_panel(summary_context)
                    start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                    return [_html_page(APP_TITLE, sidebar, content)]

                summary_context = _safe_build_summary_context()

                sidebar = _sidebar_panel(profile, summary_context, evaluate_profile_eligibility(profile))
                content = _render_alert(
                    f"Saved {saved_rows} rating rows in results.csv. The current evaluation status is shown below.",
                    "ok",
                ) + _render_evaluation_panel(summary_context)
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [_html_page(APP_TITLE, sidebar, content)]

            profile = parse_profile_form(form_data)
            eligibility = evaluate_profile_eligibility(profile)
            sidebar = _sidebar_panel(profile, summary_context, eligibility)

            if action == "evaluate":
                content = _render_evaluation_panel(summary_context)
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [_html_page(APP_TITLE, sidebar, content)]

            if not eligibility.get("eligible"):
                content = _render_alert("Not eligible.", "warn")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [_html_page(APP_TITLE, sidebar, content)]

            context = build_model_context(profile)
            if not context.eligibility.get("eligible") or not context.flat_candidates:
                content = _summary_panel(context) + _render_no_results_panel(context)
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [_html_page(APP_TITLE, sidebar, content)]

            grouped_results = _run_models(context)
            content = _render_results_panel(context, grouped_results, uuid4().hex)
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [_html_page(APP_TITLE, sidebar, content)]

        start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Method Not Allowed"]

    except Exception as exc:
        summary_context = _safe_build_summary_context()
        profile = _clone_profile()
        sidebar = _sidebar_panel(profile, summary_context, evaluate_profile_eligibility(profile))
        content = f"""
        <div class="panel">
          <h2>Unexpected Error</h2>
          <p class="muted">The evaluator hit an exception while processing the request.</p>
          <pre>{escape(str(exc))}</pre>
        </div>
        """
        start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
        return [_html_page(APP_TITLE, sidebar, content)]


def serve(host: str = HOST, port: int = PORT) -> None:
    with make_server(host, port, application) as server:
        print(f"{APP_TITLE} running at http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    serve()
