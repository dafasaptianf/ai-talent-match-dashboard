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