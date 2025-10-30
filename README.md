# AI Talent Match Intelligence Dashboard

An **AI-powered HR analytics dashboard** designed to identify and benchmark top-performing employees based on **multi-domain talent variables (TGVs)**.  
This project integrates **SQL-based intelligence**, **Supabase database**, and **Streamlit visualization** to simulate a data-driven talent selection and succession planning system.

---

## Overview

### Objective
To analyze and model what differentiates *high-performing employees* (Rating 5) using historical HR data, and to transform these insights into a **Talent Match Engine** that can:
- Identify employee readiness for key roles  
- Benchmark new candidates against high-performer profiles  
- Generate AI-based insights for HR decision-making  

### Key Deliverables
1. **AI Talent Match Dashboard** (Streamlit)
2. **Success Formula SQL Logic** (rule-based engine)
3. **Analytical Report**
4. **Dataset & Preprocessing**
5. **Supabase Integration**

---

## System Architecture

```mermaid
flowchart TD
A[Supabase Database] --> B[SQL Scoring Engine (CTE Query)]
B --> C[exec_sql() RPC Function]
C --> D[Streamlit App]
D --> E[AI Insight Generator (OpenRouter API)]
```

link dashboard: https://ai-talent-match-dashboard.streamlit.app/
