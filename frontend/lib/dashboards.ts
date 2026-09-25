/** Types des réponses de tableaux de bord (squelette phase 1). */

export interface Pending {
  value: null;
  available_in_phase: number;
}

export interface Breakdown {
  key: string | null;
  label: string | null;
  count: number;
}

export interface AdvisorDashboard {
  kpis: {
    pmes_followed: number;
    pmes_inactive: number;
    pmes_onboarded_this_month: number;
    diagnostics_to_validate: number;
    diagnostics_in_progress: number;
    pmes_urgent: number;
    documents_to_verify: number;
    alerts_open: number;
    alerts_critical: number;
    deadlines_this_week: number;
    deadlines_overdue: number;
    actions_overdue: Pending;
  };
  by_lifecycle: Breakdown[];
  recent_pmes: {
    id: string;
    legal_name: string;
    lifecycle_status: string;
    sector__name: string | null;
    last_activity_at: string | null;
    global_score: number | null;
    priority: string | null;
  }[];
  work_queue: {
    items: { kind: string; id: string; pme_id: string; pme_name: string; label: string; severity?: string; since: string | null }[];
    available_in_phase: number;
  };
  inactivity_days: number;
}

export interface PortfolioDashboard {
  kpis: {
    pmes_total: number;
    pmes_new_this_month: number;
    pmes_accompanied: number;
    pmes_active: number;
    pmes_inactive: number;
    pmes_without_advisor: number;
    pmes_diagnosed: number;
    average_score: number | null;
    median_score: number | null;
    average_progress: number | null;
    average_confidence: number | null;
    low_confidence_share: number | null;
    pmes_at_risk: number;
    pmes_urgent: number;
    average_compliance: { value: number | null; pmes: number };
  };
  by_maturity: Breakdown[];
  by_priority: Breakdown[];
  weaknesses: { code: string; name: string; weak: number; evaluated: number; share: number }[];
  weakness_threshold: number;
  progress: { top: ProgressRow[]; stagnating: ProgressRow[] };
  urgent: { pme_id: string; pme_name: string; global_score: number | null; risk_index: number | null }[];
  min_cell: number;
  by_lifecycle: Breakdown[];
  by_sector: Breakdown[];
  by_region: Breakdown[];
  by_size: Breakdown[];
  inactivity_days: number;
}

export interface PmeDashboard {
  pme: { id: string; legal_name: string; trade_name: string; lifecycle_status: string; sector: string | null };
  advisor: { full_name: string; email: string; phone: string } | null;
  score: {
    global_score: number | null;
    maturity_level: number | null;
    maturity_label: string | null;
    confidence: number;
    confidence_label: string | null;
    priority: string;
    reference_date: string;
    delta_since_baseline: number | null;
    baseline_date: string | null;
  } | null;
  open_diagnostic: { id: string; type: string; status: string; reference_date: string } | null;
  next_actions: { items: unknown[]; available_in_phase: number };
  compliance: ComplianceRate;
  feedback: { id: string; title: string; status: string; reason: string; decided_at: string }[];
  deadlines: { id: string; label: string; period: string; due_date: string; status: string; document_type: string }[];
}

export interface ProgressRow {
  pme_id: string;
  pme_name: string;
  delta: number;
  months: number;
  from: number | null;
  to: number | null;
}

export interface ComplianceRate {
  rate: number | null;
  eligible: number;
  points: number;
  counts: Record<string, number>;
}
