from __future__ import annotations

import html

import streamlit as st


# ============================================================
# BANSA UI V2
# ============================================================
#
# Shared presentation layer only.
#
# No finance logic.
# No database logic.
# No RAG logic.
# No local-agent logic.
# No network dependency.
# ============================================================


def apply_bansa_theme() -> None:
    """Apply BANSA's shared local-first fintech UI theme."""

    st.markdown(
        """
<style>

/* ==========================================================
   BANSA DESIGN TOKENS
   ========================================================== */

:root {
    --bansa-navy-950: #07111f;
    --bansa-navy-900: #0b1728;
    --bansa-navy-800: #12243a;

    --bansa-blue: #2563eb;
    --bansa-blue-soft: #eff6ff;

    --bansa-teal: #0f9f8f;
    --bansa-teal-soft: #ecfdf8;

    --bansa-bg: #f4f7fb;
    --bansa-surface: #ffffff;
    --bansa-surface-soft: #f8fafc;

    --bansa-text: #152033;
    --bansa-text-soft: #64748b;

    --bansa-border: #e2e8f0;
    --bansa-border-strong: #cbd5e1;

    --bansa-success: #059669;
    --bansa-warning: #d97706;
    --bansa-danger: #dc2626;

    --bansa-shadow:
        0 1px 2px rgba(15, 23, 42, 0.04),
        0 8px 24px rgba(15, 23, 42, 0.06);

    --bansa-shadow-hover:
        0 2px 4px rgba(15, 23, 42, 0.05),
        0 14px 32px rgba(15, 23, 42, 0.09);

    --bansa-radius: 16px;
    --bansa-radius-small: 11px;
}


/* ==========================================================
   APP SHELL
   ========================================================== */

html,
body,
[class*="css"] {
    font-family:
        Inter,
        ui-sans-serif,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(
            circle at 92% 2%,
            rgba(37, 99, 235, 0.055),
            transparent 25rem
        ),
        radial-gradient(
            circle at 4% 92%,
            rgba(15, 159, 143, 0.045),
            transparent 28rem
        ),
        var(--bansa-bg);
}

[data-testid="stMain"] {
    background: transparent;
}

[data-testid="stMainBlockContainer"] {
    max-width: 1480px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

[data-testid="stHeader"] {
    background: rgba(244, 247, 251, 0.90);
    border-bottom: 1px solid rgba(226, 232, 240, 0.80);
    backdrop-filter: blur(12px);
}


/* ==========================================================
   TYPOGRAPHY
   ========================================================== */

h1,
h2,
h3,
h4 {
    color: var(--bansa-text);
    letter-spacing: -0.025em;
}

h1 {
    font-weight: 760 !important;
}

h2,
h3 {
    font-weight: 700 !important;
}

[data-testid="stCaptionContainer"] {
    color: var(--bansa-text-soft);
}


/* ==========================================================
   SIDEBAR
   ========================================================== */

section[data-testid="stSidebar"] {
    background:
        linear-gradient(
            180deg,
            var(--bansa-navy-950) 0%,
            var(--bansa-navy-900) 48%,
            #0d1d30 100%
        );
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}

section[data-testid="stSidebar"]
[data-testid="stSidebarContent"] {
    padding-top: 1.1rem;
}

section[data-testid="stSidebar"]
[data-testid="stMarkdownContainer"] h1,
section[data-testid="stSidebar"]
[data-testid="stMarkdownContainer"] h2,
section[data-testid="stSidebar"]
[data-testid="stMarkdownContainer"] h3,
section[data-testid="stSidebar"]
[data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"]
[data-testid="stMarkdownContainer"] span {
    color: #f8fafc;
}

section[data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.10);
}

section[data-testid="stSidebar"] button {
    border-radius: 10px;
    border-color: rgba(255, 255, 255, 0.10);
    transition:
        transform 120ms ease,
        background 120ms ease,
        border-color 120ms ease;
}

section[data-testid="stSidebar"] button:hover {
    transform: translateY(-1px);
    border-color: rgba(45, 212, 191, 0.45);
}


/* ==========================================================
   BUTTONS
   ========================================================== */

.stButton > button,
.stDownloadButton > button {
    min-height: 2.7rem;
    border-radius: var(--bansa-radius-small);
    border: 1px solid var(--bansa-border);
    font-weight: 650;
    transition:
        transform 160ms cubic-bezier(0.34, 1.56, 0.64, 1),
        box-shadow 160ms ease,
        border-color 160ms ease,
        background-color 160ms ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    transform: translateY(-2px) scale(1.012);
    box-shadow: 0 10px 24px rgba(37, 99, 235, 0.14);
    border-color: var(--bansa-blue);
    background-color: var(--bansa-blue-soft);
}

.stButton > button:active,
.stDownloadButton > button:active {
    transform: translateY(0) scale(0.99);
    box-shadow: 0 3px 10px rgba(37, 99, 235, 0.12);
}

button[kind="primary"] {
    background:
        linear-gradient(
            135deg,
            #1d4ed8,
            var(--bansa-blue)
        ) !important;
    border-color: transparent !important;
    color: #ffffff !important;
    box-shadow:
        0 7px 18px rgba(37, 99, 235, 0.19);
}

button[kind="primary"]:hover {
    background:
        linear-gradient(
            135deg,
            #1e40af,
            #1d4ed8
        ) !important;
    box-shadow: 0 12px 28px rgba(37, 99, 235, 0.30) !important;
}


/* ==========================================================
   INPUTS / SELECTS
   ========================================================== */

div[data-baseweb="select"] > div,
div[data-baseweb="base-input"],
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
textarea {
    border-radius: var(--bansa-radius-small) !important;
}

div[data-baseweb="select"] > div {
    border-color: var(--bansa-border) !important;
    background: var(--bansa-surface) !important;
}

div[data-baseweb="select"] > div:hover {
    border-color: #94a3b8 !important;
}

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
textarea {
    background: var(--bansa-surface) !important;
    border-color: var(--bansa-border) !important;
}


/* ==========================================================
   METRICS
   ========================================================== */

[data-testid="stMetric"] {
    background:
        linear-gradient(
            180deg,
            #ffffff 0%,
            #fbfdff 100%
        );
    border: 1px solid var(--bansa-border);
    border-radius: var(--bansa-radius);
    padding: 1.15rem 1.2rem;
    box-shadow: var(--bansa-shadow);
    min-height: 112px;
    transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    box-shadow: var(--bansa-shadow-hover);
    border-color: rgba(37, 99, 235, 0.35);
}

[data-testid="stMetricLabel"] {
    color: var(--bansa-text-soft);
}

[data-testid="stMetricValue"] {
    background: linear-gradient(100deg, #0b1728, #2563eb);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    font-weight: 760;
    letter-spacing: -0.035em;
}


/* ==========================================================
   CONTAINERS
   ========================================================== */

[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--bansa-surface);
    border-radius: var(--bansa-radius);
    box-shadow: var(--bansa-shadow);
    transition: box-shadow 200ms ease, transform 200ms ease;
}

[data-testid="stExpander"] {
    background: var(--bansa-surface);
    border: 1px solid var(--bansa-border);
    border-radius: var(--bansa-radius-small);
    overflow: hidden;
}


/* ==========================================================
   TABLES
   ========================================================== */

[data-testid="stDataFrame"] {
    border: 1px solid var(--bansa-border);
    border-radius: var(--bansa-radius);
    overflow: hidden;
    box-shadow: var(--bansa-shadow);
    background: var(--bansa-surface);
}


/* ==========================================================
   ALERTS
   ========================================================== */

[data-testid="stAlert"] {
    border-radius: var(--bansa-radius-small);
    border-width: 1px;
}


/* ==========================================================
   CHAT
   ========================================================== */

[data-testid="stChatMessage"] {
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid var(--bansa-border);
    border-radius: 18px;
    padding: 0.55rem 0.75rem;
    margin-bottom: 0.85rem;
    box-shadow:
        0 1px 2px rgba(15, 23, 42, 0.025),
        0 6px 18px rgba(15, 23, 42, 0.035);
    animation: bansa-message-in 260ms ease-out;
}

@keyframes bansa-message-in {
    from {
        opacity: 0;
        transform: translateY(6px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

[data-testid="stChatInput"] {
    background: rgba(244, 247, 251, 0.94);
    backdrop-filter: blur(14px);
}

[data-testid="stChatInput"] textarea {
    border-radius: 16px !important;
}


/* ==========================================================
   TOGGLES
   ========================================================== */

[data-testid="stToggle"] {
    padding-top: 0.25rem;
    padding-bottom: 0.25rem;
}


/* ==========================================================
   BANSA CUSTOM COMPONENTS
   ========================================================== */

.bansa-page-header {
    position: relative;
    overflow: hidden;

    padding:
        1.75rem
        1.9rem;

    margin:
        0
        0
        1.45rem
        0;

    background:
        linear-gradient(
            135deg,
            #ffffff 0%,
            #f6faff 42%,
            #eef7ff 78%,
            #e9f6f2 100%
        );

    border:
        1px solid
        var(--bansa-border);

    border-radius:
        22px;

    box-shadow:
        0 1px 2px rgba(15, 23, 42, 0.04),
        0 18px 40px -22px rgba(37, 99, 235, 0.22);

    animation: bansa-header-fade-in 0.5s ease-out;
}

@keyframes bansa-header-fade-in {
    from {
        opacity: 0;
        transform: translateY(-6px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.bansa-page-header::after {
    content: "";

    position:
        absolute;

    width:
        260px;

    height:
        260px;

    right:
        -90px;

    top:
        -110px;

    border-radius:
        999px;

    background:
        radial-gradient(
            circle,
            rgba(37, 99, 235, 0.16),
            rgba(15, 159, 143, 0.05) 55%,
            transparent 72%
        );

    animation: bansa-glow-pulse 6s ease-in-out infinite;
}

.bansa-page-header::before {
    content: "";
    position: absolute;
    left: -70px;
    bottom: -90px;
    width: 190px;
    height: 190px;
    border-radius: 999px;
    background: radial-gradient(
        circle,
        rgba(15, 159, 143, 0.14),
        rgba(37, 99, 235, 0.03) 60%,
        transparent 72%
    );
    animation: bansa-glow-pulse 7s ease-in-out infinite reverse;
}

@keyframes bansa-glow-pulse {
    0%, 100% { opacity: 0.75; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.08); }
}

.bansa-eyebrow {
    display:
        inline-flex;

    align-items:
        center;

    gap:
        0.45rem;

    font-size:
        0.76rem;

    font-weight:
        760;

    letter-spacing:
        0.08em;

    text-transform:
        uppercase;

    background: linear-gradient(90deg, #0f766e, #2563eb);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;

    margin-bottom:
        0.55rem;
}

.bansa-page-title {
    position:
        relative;

    z-index:
        1;

    margin:
        0;

    background: linear-gradient(100deg, #0b1728 0%, #16324f 55%, #0f766e 130%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;

    font-size:
        clamp(
            1.75rem,
            3vw,
            2.55rem
        );

    line-height:
        1.08;

    font-weight:
        780;

    letter-spacing:
        -0.045em;
}

.bansa-page-subtitle {
    position:
        relative;

    z-index:
        1;

    max-width:
        850px;

    margin:
        0.7rem
        0
        0
        0;

    color:
        var(--bansa-text-soft);

    font-size:
        1rem;

    line-height:
        1.65;
}

.bansa-status {
    display:
        inline-flex;

    align-items:
        center;

    gap:
        0.42rem;

    padding:
        0.36rem
        0.68rem;

    border-radius:
        999px;

    background:
        var(--bansa-teal-soft);

    color:
        #047857;

    border:
        1px solid
        #b7eedc;

    font-size:
        0.78rem;

    font-weight:
        700;
}

.bansa-status-dot {
    width:
        7px;

    height:
        7px;

    border-radius:
        999px;

    background:
        #10b981;

    box-shadow:
        0 0 0 4px
        rgba(16, 185, 129, 0.10);
}

.bansa-hero {
    position:
        relative;

    overflow:
        hidden;

    padding:
        2.2rem
        2.25rem;

    border-radius:
        24px;

    border:
        1px solid
        rgba(148, 163, 184, 0.24);

    background:
        linear-gradient(
            130deg,
            #081526 0%,
            #102843 58%,
            #12394a 100%
        );

    box-shadow:
        0 20px 55px
        rgba(7, 17, 31, 0.14);

    margin-bottom:
        1.4rem;
}

.bansa-hero::before {
    content: "";

    position:
        absolute;

    width:
        360px;

    height:
        360px;

    border-radius:
        50%;

    right:
        -130px;

    top:
        -170px;

    background:
        radial-gradient(
            circle,
            rgba(45, 212, 191, 0.23),
            rgba(37, 99, 235, 0.07) 50%,
            transparent 70%
        );
}

.bansa-hero-kicker {
    position:
        relative;

    z-index:
        1;

    color:
        #5eead4;

    font-size:
        0.77rem;

    font-weight:
        780;

    letter-spacing:
        0.10em;

    text-transform:
        uppercase;
}

.bansa-hero-title {
    position:
        relative;

    z-index:
        1;

    max-width:
        950px;

    margin:
        0.55rem
        0
        0;

    color:
        #ffffff;

    font-size:
        clamp(
            2rem,
            4vw,
            3.45rem
        );

    line-height:
        1.03;

    font-weight:
        790;

    letter-spacing:
        -0.055em;
}

.bansa-hero-copy {
    position:
        relative;

    z-index:
        1;

    max-width:
        780px;

    margin:
        0.9rem
        0
        0;

    color:
        #cbd5e1;

    font-size:
        1.02rem;

    line-height:
        1.7;
}

.bansa-card {
    height:
        100%;

    padding:
        1.15rem
        1.2rem;

    border:
        1px solid
        var(--bansa-border);

    border-radius:
        var(--bansa-radius);

    background:
        var(--bansa-surface);

    box-shadow:
        var(--bansa-shadow);

    transition:
        transform 140ms ease,
        box-shadow 140ms ease,
        border-color 140ms ease;
}

.bansa-card:hover {
    transform:
        translateY(-2px);

    border-color:
        #cbd5e1;

    box-shadow:
        var(--bansa-shadow-hover);
}

.bansa-card-label {
    color:
        var(--bansa-text-soft);

    font-size:
        0.78rem;

    font-weight:
        680;

    letter-spacing:
        0.025em;
}

.bansa-card-title {
    color:
        var(--bansa-text);

    font-size:
        1.08rem;

    font-weight:
        740;

    margin-top:
        0.32rem;
}

.bansa-card-copy {
    color:
        var(--bansa-text-soft);

    font-size:
        0.90rem;

    line-height:
        1.55;

    margin-top:
        0.42rem;
}




/* ==========================================================
   V39 CAMPAIGN + UI REFRESH COMPONENTS
   ========================================================== */

.bansa-insight-card {
    position: relative;
    overflow: hidden;
    min-height: 126px;
    padding: 1.05rem 1.1rem;
    border: 1px solid rgba(226, 232, 240, 0.94);
    border-radius: 18px;
    background:
        linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
    box-shadow: var(--bansa-shadow);
}

.bansa-insight-card::after {
    content: "";
    position: absolute;
    width: 118px;
    height: 118px;
    right: -52px;
    top: -58px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(37,99,235,0.13), rgba(15,159,143,0.06), transparent 72%);
}

.bansa-insight-label {
    color: var(--bansa-text-soft);
    font-size: .78rem;
    font-weight: 760;
    letter-spacing: .03em;
    text-transform: uppercase;
}

.bansa-insight-value {
    margin-top: .38rem;
    color: var(--bansa-text);
    font-size: clamp(1.45rem, 2vw, 2.05rem);
    line-height: 1.05;
    font-weight: 800;
    letter-spacing: -.045em;
}

.bansa-insight-note {
    margin-top: .42rem;
    color: var(--bansa-text-soft);
    font-size: .86rem;
    line-height: 1.45;
}

.bansa-recommendation {
    position: relative;
    overflow: hidden;
    padding: 1.15rem 1.25rem;
    border-radius: 20px;
    border: 1px solid rgba(45, 212, 191, 0.28);
    background:
        linear-gradient(135deg, rgba(236,253,248,0.96), rgba(239,246,255,0.98));
    box-shadow: 0 14px 34px rgba(15, 23, 42, 0.07);
    margin-bottom: 1rem;
}

.bansa-recommendation::before {
    content: "";
    position: absolute;
    left: -70px;
    bottom: -85px;
    width: 210px;
    height: 210px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(15,159,143,.16), transparent 72%);
}

.bansa-rec-topline {
    position: relative;
    z-index: 1;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
}

.bansa-rec-title {
    color: #0f172a;
    font-weight: 800;
    font-size: 1.05rem;
    letter-spacing: -.02em;
}

.bansa-rec-badge {
    flex: 0 0 auto;
    color: #0f766e;
    background: #ffffff;
    border: 1px solid #b7eedc;
    border-radius: 999px;
    padding: .28rem .6rem;
    font-size: .76rem;
    font-weight: 760;
}

.bansa-rec-copy {
    position: relative;
    z-index: 1;
    margin-top: .55rem;
    color: #334155;
    line-height: 1.62;
    font-size: .95rem;
}

.bansa-soft-callout {
    border: 1px dashed rgba(37,99,235,.28);
    background: rgba(239,246,255,.72);
    border-radius: 16px;
    padding: .85rem 1rem;
    color: #334155;
    font-size: .92rem;
    line-height: 1.55;
}


/* ==========================================================
   MOBILE / SMALLER SCREENS
   ========================================================== */

@media (max-width: 900px) {

    [data-testid="stMainBlockContainer"] {
        padding-left:
            1rem;

        padding-right:
            1rem;
    }

    .bansa-hero {
        padding:
            1.6rem
            1.4rem;
    }

    .bansa-page-header {
        padding:
            1.25rem
            1.25rem;
    }
}



/* ==========================================================
   V22 LIVE DEMO UI · HIGH CONTRAST + DASHBOARD POLISH
   ========================================================== */

section[data-testid="stSidebar"] {
    min-width: 305px !important;
    max-width: 330px !important;
}

section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-left: .75rem !important;
    padding-right: .75rem !important;
}

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
    opacity: 1 !important;
}

[data-testid="stDataFrame"] {
    --gdg-bg-cell: #ffffff;
}

[data-testid="stDataFrame"] + div {
    color: var(--bansa-text-soft);
}

/* ==========================================================
   V21 SIDEBAR CONTRAST + DENSE TABLE POLISH
   ========================================================== */

section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.055) !important;
    color: #eaf2ff !important;
    border: 1px solid rgba(148,163,184,0.16) !important;
    box-shadow: none !important;
    min-height: 2.85rem;
    justify-content: flex-start;
    text-align: left;
    opacity: 1 !important;
}

section[data-testid="stSidebar"] .stButton > button p,
section[data-testid="stSidebar"] .stButton > button span {
    color: inherit !important;
    opacity: 1 !important;
}

section[data-testid="stSidebar"] button[kind="primary"] {
    background: linear-gradient(135deg,#1d4ed8,#2563eb) !important;
    color: #ffffff !important;
    border-color: rgba(96,165,250,0.55) !important;
}

section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(59,130,246,0.17) !important;
    color: #ffffff !important;
    border-color: rgba(96,165,250,0.42) !important;
}

section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #aebed2 !important;
    opacity: 1 !important;
}

[data-testid="stDataFrame"] {
    width: 100% !important;
}

[data-testid="stDataFrame"] [role="columnheader"] {
    font-weight: 760 !important;
}

[data-testid="stDataFrame"] [role="gridcell"] {
    font-size: 0.88rem !important;
}

@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .bansa-hero {
        padding: 1.55rem 1.35rem;
    }
}

</style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(
    title: str,
    subtitle: str = "",
    *,
    eyebrow: str = "BANSA",
) -> None:

    safe_title = html.escape(
        str(title or "")
    )

    safe_subtitle = html.escape(
        str(subtitle or "")
    )

    safe_eyebrow = html.escape(
        str(eyebrow or "BANSA")
    )

    subtitle_html = ""

    if safe_subtitle:
        subtitle_html = (
            '<p class="bansa-page-subtitle">'
            + safe_subtitle
            + "</p>"
        )

    markup = (
        '<div class="bansa-page-header">'
        '<div class="bansa-eyebrow">'
        + safe_eyebrow
        + "</div>"
        '<div class="bansa-page-title">'
        + safe_title
        + "</div>"
        + subtitle_html
        + "</div>"
    )

    st.markdown(
        markup,
        unsafe_allow_html=True,
    )


def render_hero(
    title: str,
    subtitle: str,
    *,
    kicker: str = "BANSA",
) -> None:

    safe_title = html.escape(
        str(title or "")
    )

    safe_subtitle = html.escape(
        str(subtitle or "")
    )

    safe_kicker = html.escape(
        str(kicker or "BANSA")
    )

    markup = (
        '<div class="bansa-hero">'
        '<div class="bansa-hero-kicker">'
        + safe_kicker
        + "</div>"
        '<div class="bansa-hero-title">'
        + safe_title
        + "</div>"
        '<div class="bansa-hero-copy">'
        + safe_subtitle
        + "</div>"
        "</div>"
    )

    st.markdown(
        markup,
        unsafe_allow_html=True,
    )


def render_status_badge(
    label: str,
) -> None:

    safe_label = html.escape(
        str(label or "")
    )

    markup = (
        '<span class="bansa-status">'
        '<span class="bansa-status-dot"></span>'
        + safe_label
        + "</span>"
    )

    st.markdown(
        markup,
        unsafe_allow_html=True,
    )


def render_feature_card(
    label: str,
    title: str,
    copy: str,
) -> None:

    safe_label = html.escape(
        str(label or "")
    )

    safe_title = html.escape(
        str(title or "")
    )

    safe_copy = html.escape(
        str(copy or "")
    )

    markup = (
        '<div class="bansa-card">'
        '<div class="bansa-card-label">'
        + safe_label
        + "</div>"
        '<div class="bansa-card-title">'
        + safe_title
        + "</div>"
        '<div class="bansa-card-copy">'
        + safe_copy
        + "</div>"
        "</div>"
    )

    st.markdown(
        markup,
        unsafe_allow_html=True,
    )


# ============================================================
# BANSA UI V3 / COMPETITION SHELL
# ============================================================

_NAV_ITEMS = (
    ("home", "🏠", "Genel Bakış", "Ana_Sayfa.py"),
    ("chatbot", "💬", "BANSA Asistanı", "pages/4_Chatbot.py"),
    (
        "finance",
        "🏦",
        "Finansman Karşılaştırması",
        "pages/2_Finansman_Karsilastirmasi.py",
    ),
    (
        "campaign",
        "🎁",
        "Kampanya Karşılaştırması",
        "pages/3_Kampanya_Karsilastirmasi.py",
    ),
    (
        "cards",
        "💳",
        "Kart Karşılaştırması",
        "pages/4_Kart_Karsilastirmasi.py",
    ),
)


def render_sidebar_brand() -> None:
    """Render the compact BANSA competition brand block."""

    st.markdown(
        """
<div style="padding:.25rem .1rem .7rem .1rem">
  <div style="display:flex;align-items:center;gap:.65rem">
    <div style="width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,#2563eb,#0f9f8f);display:flex;align-items:center;justify-content:center;color:white;font-weight:800;font-size:.9rem;box-shadow:0 8px 22px rgba(37,99,235,.22)">B</div>
    <div>
      <div style="color:#fff;font-weight:800;font-size:1.08rem;letter-spacing:-.02em">BANSA</div>
      <div style="color:#94a3b8;font-size:.73rem">Doğrulanmış finans asistanı</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_nav_controls(active: str) -> None:
    """Render app navigation in the current Streamlit container."""

    for key, icon, label, path in _NAV_ITEMS:
        prefix = "● " if key == active else ""
        if st.button(
            f"{prefix}{icon}  {label}",
            key=f"bansa_nav_{active}_{key}",
            use_container_width=True,
            type="primary" if key == active else "secondary",
        ):
            if key != active:
                st.switch_page(path)


def render_sidebar_navigation(active: str = "") -> None:
    """Render the shared BANSA sidebar shell."""

    with st.sidebar:
        render_sidebar_brand()
        render_nav_controls(active)
        st.markdown("")
        st.caption("Yerel model · Resmî kaynak · Doğrulanmış veri")
        st.divider()


def render_panel_card(
    icon: str,
    title: str,
    description: str,
    badge: str,
) -> None:
    """Render a visual panel summary card without navigation behavior."""

    safe_icon = html.escape(str(icon or ""))
    safe_title = html.escape(str(title or ""))
    safe_description = html.escape(str(description or ""))
    safe_badge = html.escape(str(badge or ""))

    st.markdown(
        f"""
<div class="bansa-card" style="min-height:190px;padding:1.35rem 1.4rem">
  <div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start">
    <div style="font-size:1.65rem">{safe_icon}</div>
    <span style="font-size:.7rem;font-weight:750;color:#0f766e;background:#ecfdf8;border:1px solid #b7eedc;border-radius:999px;padding:.28rem .55rem">{safe_badge}</span>
  </div>
  <div class="bansa-card-title" style="font-size:1.17rem;margin-top:.9rem">{safe_title}</div>
  <div class="bansa-card-copy" style="font-size:.91rem;line-height:1.6">{safe_description}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_section_lead(title: str, copy: str = "") -> None:
    safe_title = html.escape(str(title or ""))
    safe_copy = html.escape(str(copy or ""))
    copy_html = (
        f'<div style="color:#64748b;font-size:.9rem;margin-top:.28rem;line-height:1.55">{safe_copy}</div>'
        if safe_copy
        else ""
    )
    st.markdown(
        f"""
<div style="margin:1.1rem 0 .7rem 0">
  <div style="font-size:1.08rem;font-weight:760;color:#152033;letter-spacing:-.02em">{safe_title}</div>
  {copy_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def render_insight_card(
    label: str,
    value: str,
    note: str = "",
) -> None:
    """Render a compact metric-style card without touching Streamlit metric state."""

    safe_label = html.escape(str(label or ""))
    safe_value = html.escape(str(value or ""))
    safe_note = html.escape(str(note or ""))
    note_html = f'<div class="bansa-insight-note">{safe_note}</div>' if safe_note else ""

    st.markdown(
        f"""
<div class="bansa-insight-card">
  <div class="bansa-insight-label">{safe_label}</div>
  <div class="bansa-insight-value">{safe_value}</div>
  {note_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def render_recommendation_box(
    title: str,
    copy: str,
    *,
    badge: str = "BANSA önerisi",
) -> None:
    """Render a jury-friendly recommendation/callout card."""

    safe_title = html.escape(str(title or ""))
    safe_copy = html.escape(str(copy or ""))
    safe_badge = html.escape(str(badge or ""))

    st.markdown(
        f"""
<div class="bansa-recommendation">
  <div class="bansa-rec-topline">
    <div class="bansa-rec-title">{safe_title}</div>
    <div class="bansa-rec-badge">{safe_badge}</div>
  </div>
  <div class="bansa-rec-copy">{safe_copy}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_soft_callout(copy: str) -> None:
    """Render a neutral explanatory callout."""

    safe_copy = html.escape(str(copy or ""))
    st.markdown(
        f'<div class="bansa-soft-callout">{safe_copy}</div>',
        unsafe_allow_html=True,
    )
