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
  output_formats?: string[];
  allowed_sources?: string[];
  allowed_tools?: string[];
  termination_criteria?: string[];
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
  generation_trace?: string[];
  evolution_trace?: string[];
  merged_into?: string;
  proximity_notes?: string[];
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
  review_type?: string;
  evidence_refs?: string[];
  findings?: string[];
  review_trace?: string[];
  confidence?: number;
  requires_revision?: boolean;
};

export type Match = {
  id: string;
  hypothesis_a: string;
  hypothesis_b: string;
  winner: string;
  rationale: string;
  elo_before: Record<string, number>;
  elo_after: Record<string, number>;
  comparison_mode?: string;
  judge_trace?: string;
  uncertainty?: number;
  review_refs?: string[];
  evidence_refs?: string[];
  debate_transcript?: string[];
  outcome?: string;
};

export type ProximityEdge = {
  source: string;
  target: string;
  similarity: number;
  method?: string;
  reason?: string;
  cluster_id?: string;
  evidence_refs?: string[];
  review_refs?: string[];
  deduplication_action?: string;
  diversity_action?: string;
  exploration_trace?: string[];
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

export type CapabilityEvaluation = {
  id: string;
  baseline_name: string;
  baseline_score: number;
  code_scientist_score: number;
  beats_baseline: boolean;
  top_hypothesis_id: string;
  elo_human_correlation: number;
  elo_benchmark_correlation: number;
  candidate_count: number;
  summary: string;
  human_score_count?: number;
  benchmark_score_count?: number;
  human_rubric_judgment_count?: number;
  human_rubric_criteria?: string[];
  human_preference_judgment_count?: number;
  human_preference_win_rate?: number;
};

export type ProspectiveEvaluation = {
  id: string;
  hypothesis_id: string;
  status: string;
  implementation_refs: string[];
  baseline_metrics: Record<string, number>;
  measured_metrics: Record<string, number>;
  deltas: Record<string, number>;
  success: boolean;
  notes: string[];
};

export type ScalingCurvePoint = {
  id: string;
  label: string;
  cycles: number;
  task_count: number;
  tool_budget: number;
  baseline_score: number;
  code_scientist_score: number;
  delta: number;
  notes: string[];
};

export type SafetyEvaluationResult = {
  id: string;
  suite_name: string;
  case_count: number;
  passed_count: number;
  failed_count: number;
  pass_rate: number;
  failed_case_ids: string[];
  notes: string[];
};

export type FeedbackLoopEvaluation = {
  id: string;
  cycle: number;
  source_meta_review_id: string;
  feedback_agents: string[];
  feedback_item_count: number;
  adopted_feedback_count: number;
  adoption_rate: number;
  baseline_quality: Record<string, number>;
  observed_quality: Record<string, number>;
  deltas: Record<string, number>;
  artifact_refs: string[];
  summary: string;
  measurement_source?: string;
  measurement_status?: string;
};

export type MetaReview = {
  id: string;
  common_weaknesses: string[];
  safety_concerns: string[];
  missing_evidence: string[];
  promising_directions: string[];
  prompt_feedback: string[];
  agent_feedback?: Record<string, string[]>;
  evidence_refs?: string[];
};

export type ResearchOverview = {
  id: string;
  summary: string;
  top_hypothesis_ids: string[];
  promising_directions: string[];
  next_experiments: string[];
  limitations: string[];
  generated_by: string;
};

export type ResearchOutputArtifact = {
  id: string;
  output_type: string;
  title: string;
  summary: string;
  sections: Record<string, string>;
  related_hypothesis_ids: string[];
  contact_targets: string[];
  evidence_refs: string[];
};

export type UserFeedback = {
  id: string;
  kind: string;
  target_id: string;
  content: string;
  influence: string;
};

export type LlmInteraction = {
  turn: string;
  prompt: string;
  response: string;
  max_tokens: string;
};

export type AgentTrace = {
  id: string;
  cycle: number;
  agent: string;
  action: string;
  task_id?: string;
  input_refs: string[];
  output_refs: string[];
  status: string;
  notes: string;
  evidence_refs: string[];
  llm_interactions?: LlmInteraction[];
  scratchpad?: string[];
};

export type RetrievalMemoryRecord = {
  id: string;
  cycle: number;
  agent: string;
  task_id: string;
  query: string;
  retrieval_method: string;
  evidence_refs: string[];
  citations: string[];
  reason: string;
};

export type Task = {
  id: string;
  kind: string;
  priority: number;
  payload: Record<string, unknown>;
  status: string;
  attempts: number;
  result_refs: string[];
  error: string;
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
  run_status?: string;
  plan?: ResearchPlanConfig | null;
  evidence: unknown[];
  hypotheses: Hypothesis[];
  reviews: Review[];
  matches: Match[];
  proximity_edges?: ProximityEdge[];
  benchmark_results?: BenchmarkResult[];
  capability_evaluations?: CapabilityEvaluation[];
  prospective_evaluations?: ProspectiveEvaluation[];
  scaling_curve?: ScalingCurvePoint[];
  safety_evaluations?: SafetyEvaluationResult[];
  feedback_loop_evaluations?: FeedbackLoopEvaluation[];
  research_output_artifacts?: ResearchOutputArtifact[];
  meta_reviews: MetaReview[];
  context_snapshots?: ContextSnapshot[];
  safety: SafetyDecision | null;
  research_overview?: ResearchOverview | null;
  user_feedback?: UserFeedback[];
  agent_traces?: AgentTrace[];
  retrieval_memory?: RetrievalMemoryRecord[];
  task_queue?: Task[];
};

export type RunSummary = {
  id: string;
  objective: string;
  statePath: string;
  reportPath: string | null;
  updatedAt: string;
  runStatus: string;
  latestCycle: number | null;
  hypothesisCount: number;
  reviewCount: number;
  matchCount: number;
  safetyAllowed: boolean | null;
  readable: boolean;
  error?: string;
};
