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
    documents_to_verify: Pending;
    alerts_open: Pending;
    diagnostics_to_validate: Pending;
    actions_overdue: Pending;
    deadlines_this_week: Pending;
  };
  by_lifecycle: Breakdown[];
  recent_pmes: {
    id: string;
    legal_name: string;
    lifecycle_status: string;
    sector__name: string | null;
    last_activity_at: string | null;
  }[];
  work_queue: { items: unknown[]; available_in_phase: number };
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
    average_score: Pending;
    average_progress: Pending;
    average_compliance: Pending;
    pmes_at_risk: Pending;
    pmes_urgent: Pending;
  };
  by_lifecycle: Breakdown[];
  by_sector: Breakdown[];
  by_region: Breakdown[];
  by_size: Breakdown[];
  inactivity_days: number;
}

export interface PmeDashboard {
  pme: { id: string; legal_name: string; trade_name: string; lifecycle_status: string; sector: string | null };
  advisor: { full_name: string; email: string; phone: string } | null;
  score: Pending;
  next_actions: { items: unknown[]; available_in_phase: number };
  compliance: Pending;
  feedback: { items: unknown[]; available_in_phase: number };
  deadlines: { items: unknown[]; available_in_phase: number };
}
