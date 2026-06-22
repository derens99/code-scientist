export type ResearchGoal = {
  id: string;
  objective: string;
  domain: string;
  preferences: string[];
  constraints: string[];
  metrics: string[];
  safety_notes: string[];
};

export type ResearchPlanConfig = {
  id: string;
  goal_id: string;
  proposal_preferences: string[];
  evaluation_criteria: string[];
  generation_methods: string[];
  review_types: string[];
  evolution_strategies: string[];
  scheduler_weights: Record<string, number>;
  constraints: string[];
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

export type ProximityEdge = {
  source: string;
  target: string;
  similarity: number;
};

export type BenchmarkResult = {
  id: string;
  name: string;
  source: string;
  baseline_metrics: Record<string, number>;
  candidate_metrics: Record<string, number>;
  deltas: Record<string, number>;
  success: boolean;
  notes: string[];
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

export type ContextSnapshot = {
  id: string;
  cycle: number;
  generated_total: number;
  accepted_total: number;
  review_total: number;
  match_total: number;
  meta_review_total: number;
  top_hypothesis_ids: string[];
  origin_counts: Record<string, number>;
  status_counts: Record<string, number>;
  proximity_edge_count: number;
  scheduler_weights: Record<string, number>;
  next_actions: string[];
};

export type RunState = {
  goal: ResearchGoal;
  plan?: ResearchPlanConfig | null;
  evidence: unknown[];
  hypotheses: Hypothesis[];
  reviews: Review[];
  matches: Match[];
  proximity_edges?: ProximityEdge[];
  benchmark_results?: BenchmarkResult[];
  meta_reviews: MetaReview[];
  context_snapshots?: ContextSnapshot[];
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
