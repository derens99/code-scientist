export type ResearchGoal = {
  id: string;
  objective: string;
  domain: string;
  preferences: string[];
  constraints: string[];
  metrics: string[];
  safety_notes: string[];
};

export type TestPlan = {
  experiment: string;
  metrics: string[];
  success_condition: string;
};

export type Hypothesis = {
  id: string;
  title: string;
  claim: string;
  rationale: string;
  assumptions: string[];
  evidence_refs: string[];
  test_plan: TestPlan;
  risks: string[];
  origin: string;
  parent_ids: string[];
  elo: number;
  status: string;
};

export type Review = {
  id: string;
  hypothesis_id: string;
  decision: string;
  scores: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  safety_notes: string[];
};

export type Match = {
  id: string;
  hypothesis_a: string;
  hypothesis_b: string;
  winner: string;
  rationale: string;
  elo_before: Record<string, number>;
  elo_after: Record<string, number>;
};

export type MetaReview = {
  id: string;
  common_weaknesses: string[];
  safety_concerns: string[];
  missing_evidence: string[];
  promising_directions: string[];
  prompt_feedback: string[];
};

export type SafetyDecision = {
  allowed: boolean;
  reason: string;
  flags: string[];
};

export type RunState = {
  goal: ResearchGoal;
  evidence: unknown[];
  hypotheses: Hypothesis[];
  reviews: Review[];
  matches: Match[];
  meta_reviews: MetaReview[];
  safety: SafetyDecision | null;
};

export type RunSummary = {
  id: string;
  objective: string;
  statePath: string;
  reportPath: string | null;
  updatedAt: string;
  hypothesisCount: number;
  reviewCount: number;
  matchCount: number;
  safetyAllowed: boolean | null;
  readable: boolean;
  error?: string;
};
