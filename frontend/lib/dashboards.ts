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
    actions_overdue: number;
    actions_to_verify: number;
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
    pmes_late: number;
    actions_done: number;
    actions_overdue: number;
    progress_pmes: number;
    average_compliance: { value: number | null; pmes: number };
  };
  definitions: Record<string, string>;
  quadrant_thresholds: { imo_threshold: number; ipe_threshold: number };
  refreshed_at: string | null;
  accompanied_by_sector: Breakdown[];
  accompanied_by_region: Breakdown[];
  accompanied_by_size: Breakdown[];
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
  next_actions: {
    plan: { id: string; status: string; to_accept: boolean; done: number; total: number; in_progress: number; overdue: number } | null;
    items: { id: string; human_ref: string; title: string; status: string; due_date: string; overdue: boolean }[];
  };
  compliance: ComplianceRate;
  feedback: { id: string; title: string; status: string; reason: string; decided_at: string }[];
  deadlines: { id: string; label: string; period: string; due_date: string; status: string; document_type: string }[];
  evolution: { code: string; name: string; initial: number | null; current: number | null }[];
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

/** Ligne du tableau de portefeuille (Document 9, § 3). */
export interface PortfolioRow {
  pme_id: string;
  legal_name: string;
  sector_name: string | null;
  region_name: string | null;
  size_category: string | null;
  lifecycle_status: string;
  maturity_level: number | null;
  maturity_label: string | null;
  current_score: number | null;
  trend_6m: number | null;
  imo: number | null;
  ipe: number | null;
  quadrant: string | null;
  confidence: number | null;
  compliance_rate: number | null;
  risk_index: number | null;
  intervention_priority: string | null;
  actions_overdue: number;
  alerts_high: number;
  last_activity_at: string | null;
}

export interface ShareRow {
  code: string;
  name: string;
  weak: number;
  evaluated: number;
  share: number;
}

/** Analyses de portefeuille (Document 9, § 4.2). */
export interface PortfolioAnalyses {
  frequent_problems: { threshold: number; weak_level: number; dimensions: ShareRow[]; criteria: ShareRow[] };
  demanded_offers: { code: string; title: string; dimension: string; pmes: number }[];
  sector_heatmap: {
    min_cell: number;
    sectors: { code: string; name: string }[];
    dimensions: { code: string; name: string }[];
    cells: { sector: string; dimension: string; n: number; average: number | null }[];
  };
  trajectories: {
    top: (ProgressRow & { current: number | null })[];
    stagnating: (ProgressRow & { current: number | null })[];
    distribution: { label: string; count: number }[];
    measured: number;
    notice: string;
  };
  reinforced_support: {
    pme_id: string;
    pme_name: string;
    priority: string;
    reason: string | null;
    global_score: number | null;
    risk_index: number | null;
    actions_overdue: number;
    alerts_high: number;
  }[];
  offer_effectiveness: {
    offers: {
      code: string;
      title: string;
      criteria: string[];
      treated_n: number;
      treated_delta: number | null;
      compared_n: number;
      compared_delta: number | null;
    }[];
    unit: string;
    notice: string;
  };
  missing_deliverables: MissingDeliverables;
  regional_map: RegionalMap;
  refreshed_at: string | null;
}

export interface MissingDeliverables {
  grace_days: number;
  min_cell: number;
  deliverables: {
    code: string;
    name: string;
    requested: number;
    missing: number;
    missing_rate: number;
    average_delay_days: number | null;
    small_sample: boolean;
  }[];
  documents: {
    code: string;
    name: string;
    due: number;
    missing: number;
    late: number;
    missing_rate: number;
    average_delay_days: number | null;
    small_sample: boolean;
  }[];
}

export interface RegionalMap {
  regions: {
    code: string;
    name: string;
    pmes: number;
    scored: number;
    average_score: number | null;
    at_risk_share: number | null;
    masked: boolean;
  }[];
  without_region: number;
  min_cell: number;
  risk_threshold: number;
}
