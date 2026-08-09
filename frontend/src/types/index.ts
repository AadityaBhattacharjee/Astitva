/**
 * Astitva domain types matching the FastAPI backend schemas.
 */

export type ISODateString = string;

export type MilestoneStatus = "not_started" | "in_progress" | "completed" | "blocked";
export type Priority = "critical" | "high" | "medium" | "low";
export type StageKey = "safety" | "stability" | "financial" | "career" | "growth";
export type LifeTier = "safety" | "stability" | "growth";

export type OpportunityCategory =
  | "legal"
  | "healthcare"
  | "employment"
  | "finance"
  | "education"
  | "government"
  | "ngo"
  | "counselling"
  | "shelter";

export type Urgency = "immediate" | "soon" | "planned";

// Backend auth
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// Backend user
export interface BackendUser {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
}

// Backend profile
export interface BackendProfile {
  id: number;
  user_id: number;
  full_name: string | null;
  state: string | null;
  language: string | null;
}

// Backend scheme
export interface BackendScheme {
  id: number;
  scheme_id: string;
  scheme_name: string;
  description: string | null;
  category: string | null;
  state: string | null;
  target_group: string | null;
  benefits: string[];
  required_documents: string[];
  application_process: string | null;
  official_url: string | null;
  active_status: boolean;
}

// Agent response shapes
export interface AgentBaseResponse {
  agent_name: string;
  status: string;
}

export interface GovernmentAgentResponse extends AgentBaseResponse {
  answer: string;
  recommended_schemes: Record<string, unknown>[];
  additional_context: string;
  evidence_summary: Record<string, number>;
  sources: string[];
}

export interface SupervisorResponse extends AgentBaseResponse {
  summary: string;
  routed_to: string | null;
  intent: string;
  method: string;
}

export interface DocumentAgentResponse extends AgentBaseResponse {
  answer: string;
  guidance: Record<string, unknown>[];
  required_documents: string[];
  evidence_summary: Record<string, unknown>;
  sources: string[];
}

export interface CaseWorkerResponse extends AgentBaseResponse {
  case_summary: string;
  priority_actions: Record<string, unknown>[];
  document_gaps: string[];
  roadmap_status: string;
  risk_flags: string[];
  case_meta: Record<string, unknown>;
}

export interface EmploymentAgentResponse extends AgentBaseResponse {
  answer: string;
  job_options: Record<string, unknown>[];
  skills_guidance: string[];
  next_actions: string[];
  evidence_summary: Record<string, unknown>;
  sources: string[];
}

export interface FinanceAgentResponse extends AgentBaseResponse {
  answer: string;
  financial_options: Record<string, unknown>[];
  budgeting_tips: string[];
  next_actions: string[];
  disclaimer: string;
  evidence_summary: Record<string, unknown>;
  sources: string[];
}

export interface HealthcareAgentResponse extends AgentBaseResponse {
  answer: string;
  healthcare_schemes: Record<string, unknown>[];
  next_actions: string[];
  medical_disclaimer: string;
  evidence_summary: Record<string, unknown>;
  sources: string[];
}

export interface LegalAgentResponse extends AgentBaseResponse {
  answer: string;
  legal_information: Record<string, unknown>[];
  suggested_resources: string[];
  next_actions: string[];
  legal_disclaimer: string;
  evidence_summary: Record<string, unknown>;
  sources: string[];
}

export interface MentorMatchingResponse extends AgentBaseResponse {
  answer: string;
  ideal_mentor_profile: Record<string, unknown>;
  recommended_channels: string[];
  next_actions: string[];
  disclaimer: string;
  no_mentor_db: boolean;
  profile_used: Record<string, unknown>;
}

export interface PlanningAgentResponse extends AgentBaseResponse {
  answer: string;
  existing_plan_summary: Record<string, unknown>;
  recommended_next_actions: Record<string, unknown>[];
  gaps_identified: string[];
  disclaimer: string;
  context_meta: Record<string, unknown>;
}

export interface ProgressAgentResponse extends AgentBaseResponse {
  answer: string;
  progress_summary: Record<string, unknown>;
  achievements: string[];
  pending_actions: string[];
  next_recommended_step: string;
  context_meta: Record<string, unknown>;
}

export interface RiskAgentResponse extends AgentBaseResponse {
  answer: string;
  risk_level: string;
  risk_score: number;
  risk_flags: string[];
  risk_interpretation: string;
  observed_risk_factors: string[];
  inferred_risk_factors: string[];
  recommended_interventions: string[];
  risk_features: Record<string, unknown>;
  context_meta: Record<string, unknown>;
}

// Backend roadmap
export interface BackendRoadmap {
  id: number;
  user_id: number;
  title: string;
  summary: string | null;
  status: string;
  tasks: BackendRoadmapTask[];
}

export interface BackendRoadmapTask {
  id: number;
  roadmap_id: number;
  title: string;
  description: string | null;
  status: string;
  priority: string;
}

// Backend progress
export interface BackendProgress {
  id: number;
  roadmap_id: number;
  status: string;
  completed_milestones: number;
  missed_milestones: number;
  overdue_tasks: number;
}

// UI-only types
export interface ChatMessage {
  id: string;
  role: "user" | "guide";
  text: string;
  at: ISODateString;
  agentType?: string;
  sources?: string[];
}

export interface SettingsState {
  language: string;
  voiceEnabled: boolean;
  notifications: boolean;
  lowBandwidth: boolean;
  dataSharingConsent: boolean;
  highContrast: boolean;
}

export interface Assessment {
  ageRange: string;
  location: string;
  situation: string[];
  employmentStatus: string;
  financialSituation: string;
  dependents: string;
  safetyConcern: string;
  housing: string;
  healthcareNeeds: string[];
  legalNeeds: string[];
  careerNeeds: string[];
  educationNeeds: string[];
  financialNeeds: string[];
  language: string;
  communicationPreference: string;
  constraints: string[];
  goals: string[];
}
