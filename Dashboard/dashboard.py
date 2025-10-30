import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client
import uuid
import requests

# ========== PAGE CONFIG ==========
st.set_page_config(page_title="AI Talent Match Dashboard", layout="wide")

# ========== SUPABASE CONNECTION ==========
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ========== SIDEBAR INPUT ==========
st.sidebar.header(" Job Vacancy Parameters")

role = st.sidebar.text_input("Role Name", "Data Engineer")
level = st.sidebar.selectbox("Job Level", ["Staff", "Senior", "Manager"])
purpose = st.sidebar.text_area("Role Purpose", "Responsible for building scalable data pipelines.")

try:
    employees_resp = supabase.table("employees").select("employee_id, fullname").execute()
    employees = employees_resp.data or []
except Exception as e:
    st.sidebar.error(f"Gagal mengambil data dari Supabase: {e}")
    employees = []

if not employees:
    st.sidebar.warning("Table employees kosong. Mencoba ambil data dari competencies_yearly.")
    try:
        emp_fallback = supabase.table("competencies_yearly").select("employee_id").execute()
        emp_ids = list({e["employee_id"] for e in emp_fallback.data})  # unique IDs
        employees = [{"employee_id": e, "fullname": f"Employee {i+1}"} for i, e in enumerate(emp_ids)]
    except Exception as e:
        st.sidebar.error(f"Tidak ada data employee_id di Supabase. Error: {e}")
        employees = []

if not employees:
    st.sidebar.error("Tidak ada employee_id di Supabase. Harap isi data di tabel employees / competencies_yearly.")
    st.stop()

employee_list = [e["employee_id"] for e in employees]
employee_names = [e.get("fullname", e["employee_id"]) for e in employees]

benchmarks = st.sidebar.multiselect(
    "Select Benchmark Employees",
    options=employee_list,
    format_func=lambda eid: next((e["fullname"] for e in employees if e["employee_id"] == eid), eid),
    default=employee_list[:3] if len(employee_list) >= 3 else employee_list
)

if not benchmarks:
    st.sidebar.warning(" No benchmark employees selected. Please select at least one.")
    st.stop()

run_btn = st.sidebar.button(" Run Talent Match Analysis")


# Pastikan state disiapkan
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None
if "leaderboard" not in st.session_state:
    st.session_state.leaderboard = None

def make_uuid_array_str(ids):
    """Format list UUID menjadi format array PostgreSQL valid."""
    if not ids:
        return "ARRAY[]::uuid[]"
    quoted = ",".join(f"'{str(i)}'" for i in ids)
    return f"ARRAY[{quoted}]::uuid[]"

def make_uuid_list_str(ids):
    if not ids:
        return "''"
    return ",".join(f"'{str(i)}'" for i in ids)

if run_btn:
    st.title(" AI Talent Match Intelligence Dashboard")

    # 1Insert or parameterize a new job_vacancy_id
    job_vacancy_id = str(uuid.uuid4())

    # Pastikan benchmark disimpan sebagai text list
    benchmarks = [str(b) for b in benchmarks]

    if not benchmarks:
        st.error("No benchmark employees selected or found. Please check Supabase data or CSV.")
        st.stop()

    supabase.table("talent_benchmarks").insert({
        "job_vacancy_id": job_vacancy_id,
        "role_name": role,
        "job_level": level,
        "purpose": purpose,
        "benchmark_employee_ids": benchmarks
    }).execute()

    # Buat array string dulu di luar query
    benchmarks_array = make_uuid_array_str(benchmarks)
    benchmarks_str = make_uuid_list_str(benchmarks)

    # 2 & 3 Query recomputed data dynamically from Supabase
    query = f"""
    WITH benchmark_iq AS (
        SELECT 
            PERCENTILE_CONT(0.5)
            WITHIN GROUP (ORDER BY iq) AS baseline_score
        FROM profiles_psych p
        WHERE p.employee_id::text IN ({benchmarks_str})
    ),

    employee_pillars_with_detail AS (
        SELECT 
            employee_id,
            AVG(score) AS avg_pillar_score,
            MAX(CASE WHEN pillar_code = 'GDR' THEN score END) AS gdr,
            MAX(CASE WHEN pillar_code = 'CEX' THEN score END) AS cex
        FROM competencies_yearly
        GROUP BY employee_id
    ),

    employee_strengths AS (
        SELECT 
            e.employee_id,
            ARRAY_AGG(DISTINCT s.theme) AS strengths
        FROM employees e
        JOIN strengths s ON e.employee_id::text = s.employee_id::text
        GROUP BY e.employee_id
    ),

    employee_iq AS (
        SELECT 
            e.employee_id, p.iq, p.mbti, p.disc
        FROM employees e
        JOIN profiles_psych p ON e.employee_id::text = p.employee_id::text
    ),

    employee_context AS (
        SELECT 
            e.employee_id,
            ed.name AS education_name,
            e.years_of_service_months
        FROM employees e
        JOIN dim_education ed ON e.education_id = ed.education_id
    ),

    -- === TGV1: Core Competencies ===
    tgv1 AS (
        SELECT 
            ep.employee_id,
            'Core Competencies' AS tgv_name,
            'Average of 10 Pillars' AS tv_name,
            1.0 AS baseline_score,
            ROUND(
                (LEAST(
                    ((ep.avg_pillar_score / 5.0)
                    + CASE WHEN ep.gdr >= 4.0 THEN 0.1 ELSE 0 END
                    + CASE WHEN ep.cex >= 4.0 THEN 0.1 ELSE 0 END),
                    1.0
                ) * 100)::numeric, 2
            ) AS tv_match_rate,
            ROUND(
                (LEAST(
                    ((ep.avg_pillar_score / 5.0)
                    + CASE WHEN ep.gdr >= 4.0 THEN 0.1 ELSE 0 END
                    + CASE WHEN ep.cex >= 4.0 THEN 0.1 ELSE 0 END),
                    1.0
                ) * 100)::numeric, 2
            ) AS tgv_match_rate
        FROM employee_pillars_with_detail ep
    ),

    -- === TGV2: Behavioral Profile ===
    tgv2 AS (
        SELECT 
            es.employee_id,
            'Behavioral Profile' AS tgv_name,
            'Top 5 Strengths' AS tv_name,
            100 AS baseline_score,
            CASE 
                WHEN ARRAY['Positivity', 'Futuristic'] && es.strengths THEN 100
                ELSE 80
            END AS tv_match_rate,
            CASE 
                WHEN ARRAY['Positivity', 'Futuristic'] && es.strengths THEN 100
                ELSE 80
            END AS tgv_match_rate
        FROM employee_strengths es
    ),

    -- === TGV3: Cognitive & Personality ===
    tgv3 AS (
        SELECT 
            ei.employee_id,
            'Cognitive & Personality Profile' AS tgv_name,
            'IQ Score' AS tv_name,
            bi.baseline_score,
            ROUND(LEAST((ei.iq / NULLIF(bi.baseline_score,0)) * 100, 100)::numeric, 2) AS tv_match_rate,
            ROUND(LEAST((ei.iq / NULLIF(bi.baseline_score,0)) * 100, 100)::numeric, 2) AS tgv_match_rate
        FROM employee_iq ei
        CROSS JOIN benchmark_iq bi
    ),

    -- === TGV4: Context & Experience ===
    tgv4 AS (
        SELECT 
            ec.employee_id,
            'Context & Experience' AS tgv_name,
            'Education & Years of Service' AS tv_name,
            100 AS baseline_score,
            CASE
                WHEN ec.education_name = 'S2' AND ec.years_of_service_months >= 48 THEN 100
                WHEN ec.education_name = 'S1' AND ec.years_of_service_months >= 36 THEN 90
                WHEN ec.education_name IN ('D3', 'SMA') AND ec.years_of_service_months >= 50 THEN 85
                ELSE 70
            END AS tv_match_rate,
            CASE
                WHEN ec.education_name = 'S2' AND ec.years_of_service_months >= 48 THEN 100
                WHEN ec.education_name = 'S1' AND ec.years_of_service_months >= 36 THEN 90
                WHEN ec.education_name IN ('D3', 'SMA') AND ec.years_of_service_months >= 50 THEN 85
                ELSE 70
            END AS tgv_match_rate
        FROM employee_context ec
    ),

    combined AS (
        SELECT * FROM tgv1
        UNION ALL SELECT * FROM tgv2
        UNION ALL SELECT * FROM tgv3
        UNION ALL SELECT * FROM tgv4
    ),
    final_match AS (
        SELECT employee_id, ROUND(AVG(tgv_match_rate),2) AS final_match_rate
        FROM combined GROUP BY employee_id
    )
    SELECT 
        e.employee_id,
        e.fullname,
        d.name AS directorate,
        p.name AS position,
        g.name AS grade,
        c.tgv_name,
        c.tv_name,
        c.baseline_score,
        c.tv_match_rate,
        c.tgv_match_rate,
        f.final_match_rate
    FROM employees e
    JOIN combined c ON e.employee_id = c.employee_id
    JOIN final_match f ON e.employee_id = f.employee_id
    LEFT JOIN dim_directorates d ON e.directorate_id = d.directorate_id
    LEFT JOIN dim_positions p ON e.position_id = p.position_id
    LEFT JOIN dim_grades g ON e.grade_id = g.grade_id
    ORDER BY f.final_match_rate DESC;
    """

    # 🧹 Hapus tanda ";" di akhir query supaya tidak error di exec_sql
    query = query.strip().rstrip(";")

    # st.code(query, language="sql")
    # st.write(" Benchmarks str:", benchmarks_str)

    # st.write(" Benchmarks:", benchmarks)
    # st.write("Benchmarks_str:", benchmarks_str)

    # Eksekusi query via RPC Supabase

    response = supabase.rpc("exec_sql", {"query": query}).execute()
    # st.write("Raw RPC response:", response.data)

    if not response.data:
        st.error("No data returned from Supabase RPC. Check your SQL query or exec_sql() function.")
        st.stop()

    # Parse hasil JSON dari kolom "result"
    try:
        data = [row["result"] for row in response.data if "result" in row]
        df = pd.DataFrame(data)
        # st.success(f" {len(df)} rows loaded from Supabase.")
    except Exception as e:
        st.error(f"Failed to parse JSON result: {e}")
        st.stop()

    # --- Fix tipe data employee_id ke string ---
    if "employee_id" in df.columns:
        df["employee_id"] = df["employee_id"].astype(str)

    # st.write("Columns loaded:", list(df.columns))

    # --- Fix tipe data employee_id ke string ---
    df["employee_id"] = df["employee_id"].astype(str)

    # 4 Compute dynamic baseline from selected benchmark employees
    baseline = df[df["employee_id"].isin(benchmarks)]
    medians = (
        baseline.groupby("tv_name")["tv_match_rate"]
        .median()
        .rename("baseline_score")
        .reset_index()
    )

    merged = df.copy()

    leaderboard = (
        merged.groupby(["employee_id", "fullname", "directorate", "position"], dropna=False)
        .agg(final_score=("final_match_rate", "mean"))
        .sort_values("final_score", ascending=False)
        .reset_index()
    )


    # merged = df.merge(medians, on="tv_name", how="left")
    # merged["tv_match_rate_dynamic"] = (merged["tv_match_rate"] / merged["baseline_score"]) * 100
    # merged["tv_match_rate_dynamic"] = merged["tv_match_rate_dynamic"].clip(0, 120)
    # merged["tgv_match_rate"] = merged.groupby(["employee_id", "tgv_name"])["tv_match_rate_dynamic"].transform("mean")
    # merged["final_match_rate"] = merged.groupby("employee_id")["tgv_match_rate"].transform("mean").clip(0, 100)

    leaderboard = (
        merged.groupby(["employee_id", "fullname", "directorate", "position"])
        .agg(final_score=("final_match_rate", "mean"))
        .sort_values("final_score", ascending=False)
        .reset_index()
    )

    # Save to session
    st.session_state.analysis_data = merged
    st.session_state.leaderboard = leaderboard
    st.session_state.job_vacancy_id = job_vacancy_id

# === DISPLAY DASHBOARD ===
if st.session_state.analysis_data is not None:
    merged = st.session_state.analysis_data
    leaderboard = st.session_state.leaderboard
    job_vacancy_id = st.session_state.job_vacancy_id

    st.subheader(f"Ranked Talent List for {role} ({level})")
    st.dataframe(leaderboard.head(10), use_container_width=True)

    selected_name = st.selectbox(
        "Select Candidate to Analyze",
        leaderboard["fullname"],
        index=0,
        key="candidate_selector"
    )
    cand = merged[merged["fullname"] == selected_name]

    if cand.empty:
        st.warning("No data found for selected candidate.")
        st.stop()

    # ========== VISUALS ==========
    col1, col2 = st.columns(2)

    # --- Radar Chart ---
    with col1:
        radar = cand.groupby("tgv_name")["tgv_match_rate"].mean().reset_index()
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=radar["tgv_match_rate"],
            theta=radar["tgv_name"],
            fill='toself',
            name='TGV Match'
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 120])),
            showlegend=False,
            title="TGV Match Overview"
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    # --- Distribution Chart ---
    with col2:
        fig_dist = px.histogram(
            leaderboard, x="final_score", nbins=20,
            title="Distribution of Final Match Rate",
            color_discrete_sequence=["#0099ff"]
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    # --- Heatmap per TV ---
    st.subheader("Candidate TV Match Heatmap")
    pivot = cand.pivot_table(index="tv_name", values="tv_match_rate", aggfunc="mean")
    fig_heat = px.imshow(
        pivot, color_continuous_scale="RdYlGn", aspect="auto",
        labels=dict(color="Match Rate (%)")
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # ========== AI INSIGHT ==========
    st.markdown("### AI-Generated Insights")

    API_KEY = st.secrets.get("OPENROUTER_API_KEY", None)
    if not API_KEY:
        st.warning("Add your OpenRouter API key in .streamlit/secrets.toml to enable AI insight.")
    else:
        summary = merged.groupby("tgv_name")["tgv_match_rate"].mean().reset_index()
        text_summary = summary.to_string(index=False)

        prompt = f"""
        You are an HR Data Analyst AI assistant.
        Job Role: {role} ({level})
        Purpose: {purpose}

        Benchmark Employees: {', '.join(benchmarks)}
        Job Vacancy ID: {job_vacancy_id}
        TGV Summary:
        {text_summary}

        Generate a concise insight covering:
        1. Top strengths & gaps across TGVs
        2. Why the top candidates excel
        3. Recommendations for HR and development plans
        """

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tngtech/deepseek-r1t2-chimera:free",
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        if response.status_code == 200:
            insight = response.json()["choices"][0]["message"]["content"]
            st.success(insight)
        else:
            st.error(f"AI request failed: {response.text}")
