# Story → Initiative + Status — review sheet

First-pass mapping of all 92 stories. **Initiative** is constrained to the initiatives whose *Divisions impacted* include the story's division (per `initiatives.csv`), then chosen by best semantic fit. **Status** is *seeded* from the matched initiative's value/effort quadrant — it is a starting point, not real funding data; override freely.

Status seed rule: Quick win + Very-High value → **Funded**; other Quick win → **Endorsed**; Major bet / Fill-in → **Prioritised**; Heavy lift → **Parked**.

Totals — Status: Funded 3, Endorsed 51, Prioritised 29, Parked 9.  Match confidence: high 30, medium 41, low 21. **⚠ = low confidence, please check.**


## Portfolio & FAO

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 1 | Unit Pricing Control — the “S.U.E.” agent | Unit Price Monitoring | high | Funded | unit pricing anomaly/alerting is monitoring |
| 2 | Wrap Bank Reconciliations | Wrap Reconciliations | high | Parked | wrap bank reconciliation matching |
| 3 | RBA Cash Rate Change Handling | Automation Tooling (e.g. ROVO) | medium | Endorsed | process orchestration and checklist automation |
| 4 | Weekly Cash Rate Publication | Automation Tooling (e.g. ROVO) | medium | Endorsed | automated sourcing and validation workflow |
| 5 | Portfolio Reporting | Automation Tooling (e.g. ROVO) | medium | Endorsed | reporting extraction and deck-prep automation |

## Finance

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 6 | Document & Data Ingestion (IDP) | Invoice & PDF Extraction | high | Prioritised | invoice and tax PDF ingestion |
| 7 | Pattern-Based Variance Analysis | Finance Payments & Reconciliations | medium | Endorsed | variance analysis over payments data |
| 8 | Financial Control Risk in Payments | Finance Payments & Reconciliations | high | Endorsed | revenue payments validation control |
| 9 | Cross-System Reconciliation & Matching | Finance Payments & Reconciliations | high | Endorsed | cross-system fuzzy reconciliation matching |
| 10 | Classification Against Known Rules | Finance Payments & Reconciliations | medium | Endorsed | rule-based financial classification/refinement |
| 11 | High-Volume Mailbox & Admin | Automation Tooling (e.g. ROVO) | medium | Endorsed | email triage and routing automation |
| 12 | Reporting Pack Preparation & Assurance | Board & Committee Documents & Reports | medium | Endorsed | auto-populate reporting pack slides |
| 13 | FBI: ASX Asset Allocation, FUMA & BI | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | research agents and BI querying, no better home |

## Legal & CoSec

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 14 | Institutional Memory & Historical Retrieval | Self-Service Knowledge Bases | high | Endorsed | RAG over board papers corpus |
| 15 | Director Preparation & Meeting Readiness | Self-Service Knowledge Bases | high | Endorsed | factual Q&A with references |
| 16 | Board Paper Quality & Compliance Checking | Board & Committee Documents & Reports | medium | Endorsed | board paper quality diagnostic |
| 17 | CoSec Workflow Automation | Automation Tooling (e.g. ROVO) | medium | Endorsed | agenda/checklist workflow automation |
| 18 | ToR Compliance Monitoring | APRA Prudential Review Support | ⚠ low | Prioritised | ToR compliance monitoring/governance |
| 19 | Repeat Question Handling | Self-Service Knowledge Bases | high | Endorsed | attributed repeat-question Q&A layer |
| 20 | Post-Decision Tracking & Accountability | Automation Tooling (e.g. ROVO) | medium | Endorsed | action tracking workflow automation |

## Superannuation

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 21 | Governance Coordination | Automation Tooling (e.g. ROVO) | medium | Endorsed | agenda assembly and action-tracking automation |
| 22 | Executive (CEO) Reporting | Board & Committee Documents & Reports | medium | Endorsed | CEO reporting draft synthesis |
| 23 | SS&C Oversight | AI Model Testing / QA | ⚠ low | Prioritised | oversight anomaly/drift monitoring |
| 24 | Compliance Monitoring of Advice Calls | Call Recording Analysis | high | Prioritised | advice call transcription and analysis |

## Technology

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 25 | Information Assembly & Manual Reconstruction | ITSM / ITIL & Cyber Monitoring | medium | Prioritised | incident/change and security info assembly |
| 26 | Pattern Recognition Across Historical Data | ITSM / ITIL & Cyber Monitoring | high | Prioritised | ServiceNow/Wiz/CrowdStrike change-incident correlation |
| 27 | Repetitive Low-Complexity Demand | ITSM / ITIL & Cyber Monitoring | medium | Prioritised | ITSM triage and deflection |
| 28 | Asset & Owner Discovery (CMDB Gap) | ITSM / ITIL & Cyber Monitoring | high | Prioritised | vulnerability ownership discovery from telemetry |
| 29 | Technology Governance & Knowledge | Self-Service Knowledge Bases | high | Endorsed | tech knowledge base and decision records |
| 30 | Vendor & Third-Party Risk | ITSM / ITIL & Cyber Monitoring | medium | Prioritised | vendor cyber-risk document analysis |
| 31 | Legacy App & Test Automation | Engineering Automation (Coding, Testing) | high | Prioritised | AI test generation and code migration |

## People & Culture

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 32 | Hiring Approval Fragmentation | Insignia Staff Services Automation | medium | Prioritised | hiring approval workflow support |
| 33 | Goal Setting Quality & Cascading | Insignia Staff Services Automation | ⚠ low | Prioritised | goal drafting/screening staff process |
| 34 | JD & Remuneration Benchmarking | Automated Role Documents | high | Prioritised | JD drafting and benchmarking are role documents |
| 35 | HRSS Transactional Volume | Insignia Staff Services Automation | high | Prioritised | HRSS letters, forms, Q&A automation |
| 36 | WR Document Processing & Case Management | Insignia Staff Services Automation | medium | Prioritised | WR case management workflow support |
| 37 | Payroll Reconciliation & Compliance | Insignia Staff Services Automation | medium | Prioritised | payroll reconciliation staff service |
| 38 | Visa Auditing & Compliance Tracking | Insignia Staff Services Automation | medium | Prioritised | visa expiry monitoring and tracking |
| 39 | Compliance Learning Management | Insignia Staff Services Automation | medium | Prioritised | learning allocation and reminder automation |
| 40 | Critical Role & Succession Visibility | Insignia Staff Services Automation | ⚠ low | Prioritised | succession/talent data, no better home |
| 41 | Employee Engagement & Sentiment | Insignia Staff Services Automation | ⚠ low | Prioritised | engagement survey analysis staff service |

## Risk

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 42 | Fraud — Reactive Detection | Fraud Signal Monitoring | high | Parked | behavioural baselines and anomaly scoring |
| 43 | CRO Reporting at Scale | Board & Committee Documents & Reports | medium | Endorsed | governance report drafting at scale |
| 44 | Conduct / NFR Coordination | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | conduct obligation workflow automation |
| 45 | Regulatory Horizon Scanning | Regulatory Horizon Scanning | high | Parked | regulatory ingestion and horizon prediction |
| 46 | Risk Management Knowledge Base | Self-Service Knowledge Bases | high | Endorsed | RAG over policy/framework docs |

## Strategy & Innovation

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 47 | Knowledge Fragmentation & Retrieval | Self-Service Knowledge Bases | high | Endorsed | semantic search across M365 sources |
| 48 | Competitive & External Intelligence | Competitor Intelligence | high | Prioritised | competitor benchmarking and monitoring |
| 49 | Planning, Scorecards & Reporting | Board & Committee Documents & Reports | medium | Endorsed | scorecard narrative drafting |
| 50 | Unstructured-to-Structured Conversion | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | document parsing/normalisation, no better home |
| 51 | Low-Value Production Work | Automation Tooling (e.g. ROVO) | medium | Endorsed | Copilot deck formatting automation |
| 52 | Calendar Coordination | Automation Tooling (e.g. ROVO) | high | Endorsed | Copilot scheduling automation |
| 53 | Meeting Capture & Synthesis | Automation Tooling (e.g. ROVO) | medium | Endorsed | meeting capture and synthesis automation |

## Wrap

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 54 | The Data Assembly Tax | Wrap Reconciliations | medium | Parked | extract and reconcile disconnected data |
| 55 | Regulatory & Compliance Risk from Manual Collation | Wrap Reconciliations | ⚠ low | Parked | manual collation reconciliation risk |
| 56 | Operational Error Volume & Legacy Constraints | Automation Tooling (e.g. ROVO) | medium | Endorsed | automate manual error-prone processes |
| 57 | Call Record & Member Intelligence | Call Recording Analysis | high | Prioritised | Genesys call and sentiment analysis |
| 58 | Fragmented Strategy & Blank-Cell Teams | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | no identified use case, generic default |

## Super to Retirement

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 59 | The Advice Gap & Unmet Member Needs | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | advice journey redesign, no better home |
| 60 | SOA Production Bottleneck | SOA Production | high | Funded | AI SOA first-draft generation |
| 61 | Prospect Identification & Lead Scoring | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | lead scoring, no better home |
| 62 | Super-to-Retirement ‘Brain’ | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | proactive nudge brain, no better home |
| 63 | Member Consent & Data Reach | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | consent/privacy strategy, no better home |
| 64 | General vs Personal Advice Boundary | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | advice-tier framework, no better home |
| 65 | Adviser Productivity & Capacity | Automation Tooling (e.g. ROVO) | medium | Endorsed | adviser co-pilot productivity tools |
| 66 | Product Menu Simplification | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | cohort defaults, no better home |
| 67 | Interoperability of Engines | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | engine interoperability architecture, no better home |
| 68 | Regulatory Compliance Embedding | AI Model Testing / QA | medium | Prioritised | AI fairness and compliance governance |

## Advice

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 69 | Paraplanning Throughput | SOA Production | high | Funded | paraplanning SOA draft generation |
| 70 | CGT Calculations | CGT Calculation | high | Parked | CGT calculation with OCR parsing |
| 71 | Advice Assurance / Compliance | Advisor Efficiency Tools | medium | Endorsed | inline compliance prompting during drafting |
| 72 | Meeting Documents — Pre / Post | Advisor Efficiency Tools | high | Endorsed | pre/post meeting prep and file notes |
| 73 | Repetitive Admin — Forms, Data, Onboarding | Automation Tooling (e.g. ROVO) | medium | Endorsed | rules-based form completion automation |

## Asset Management

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 74 | Portfolio Exposure Monitoring | Automation Tooling (e.g. ROVO) | medium | Endorsed | exposure dashboard pipeline automation |
| 75 | Fragmented Data Sourcing (FUM / flows / performance) | Automation Tooling (e.g. ROVO) | medium | Endorsed | data sourcing collation automation |
| 76 | PE & Alts Document Retrieval | PE & Alternatives Portfolio Document Retrieval | high | Parked | PE portal document retrieval |
| 77 | PE & Alts Data Extraction | PE & Alternatives Portfolio Document Retrieval | high | Parked | PE/Alts document data extraction |
| 78 | IMA & Legal Document Management | PE & Alternatives Portfolio Document Retrieval | medium | Parked | IMA document querying/retrieval |
| 79 | RCR / PDS Disclosure Workflow | Automation Tooling (e.g. ROVO) | medium | Endorsed | disclosure export-to-template mapping automation |
| 80 | Market & Manager Intelligence | Competitor Intelligence | medium | Prioritised | manager/market monitoring briefings |
| 81 | Transition Planning & Scenario Modelling | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | scenario modelling, distinct from doc intel |
| 82 | Trusted / Private AI Environment | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | private AI environment enablement |
| 83 | Proxy Voting & Corporate Actions | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | proxy recommendation drafting workflow |
| 84 | Personal Trading Pre-Approvals | Personal Trading Pre-Approvals | high | Prioritised | rules-based trade pre-approval processing |

## Customer

| # | Opportunity | Initiative | Conf | Status | Why |
|---|---|---|---|---|---|
| 85 | Website Content Production | Brand Variants for Content & Tone | medium | Prioritised | AI-assisted website copy production |
| 86 | Multi-Brand Communications | Brand Variants for Content & Tone | high | Prioritised | per-brand communication adaptation |
| 87 | Compliance & Tone QA | Brand Variants for Content & Tone | medium | Prioritised | automated tone and compliance checking |
| 88 | Data Operations | Automation Tooling (e.g. ROVO) | medium | Endorsed | reusable campaign data pipeline automation |
| 89 | Campaign Reporting | Automation Tooling (e.g. ROVO) | medium | Endorsed | multi-source ingestion and reporting automation |
| 90 | Delivery Reporting | Automation Tooling (e.g. ROVO) | medium | Endorsed | Jira delivery reporting automation |
| 91 | Developer QA & Observability | AI Model Testing / QA | medium | Prioritised | AI-assisted test generation and QA |
| 92 | Corporate Affairs & Institutional Memory | Automation Tooling (e.g. ROVO) | ⚠ low | Endorsed | RAG institutional memory, no better home |
