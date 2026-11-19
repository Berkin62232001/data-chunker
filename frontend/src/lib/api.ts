const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Kept in memory only; never put access keys in NEXT_PUBLIC_* or browser storage.
let accessKey = "";

export async function unlockWorkspace(key: string): Promise<void> {
  accessKey = key;
  try {
    await apiFetch("/api/documents");
  } catch (error) {
    accessKey = "";
    throw error;
  }
}

export function lockWorkspace(): void {
  accessKey = "";
}

function authorizedHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  if (accessKey) headers.set("Authorization", `Bearer ${accessKey}`);
  return headers;
}

export interface HealthStatus {
  status: string;
  app: string;
  version: string;
  local_only_mode: boolean;
}

export async function fetchHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export interface UploadResult {
  document_id: string;
  original_filename: string;
  stored_filename: string;
  size_bytes: number;
  mime_type: string | null;
  status: string;
}

export interface DocumentProfile {
  document_id: string;
  original_filename: string;
  stored_filename: string;
  extension: string;
  mime_type: string | null;
  size_bytes: number;
  category: string;
  content_type: string | null;
  page_count: number | null;
  text_extractable: boolean | null;
  requires_ocr: boolean;
  has_text_layer: boolean | null;
  scanned_like: boolean | null;
  extracted_text_char_count: number | null;
  ocr_supported: boolean;
  ocr_reason: string | null;
  recommended_pipeline: string;
  profiled_at: string;
}

export interface PipelineDecision {
  document_id: string;
  selected_pipeline: string;
  output_format: string;
  output_artifacts: string[];
  llm_send_format_claude: string;
  llm_send_format_openai_gemini: string;
  reasons: string[];
  warnings: string[];
  decided_at: string;
}

export interface ConversionMetadata {
  document_id: string;
  original_filename: string;
  source_mime_type: string | null;
  selected_pipeline: string;
  conversion_status: string;
  created_at: string;
  output_files: string[];
  estimated_character_count: number;
  estimated_token_count: number;
}

export interface ExtractionReport {
  success: boolean;
  converter_used: string;
  warnings: string[];
  errors: string[];
  fallback_used: boolean;
  ocr_used: boolean;
  ocr_provider: string | null;
  ocr_language: string | null;
  ocr_pages_processed: number | null;
  ocr_succeeded: boolean | null;
  ocr_warnings: string[];
  ocr_error: string | null;
  ocr_text_char_count: number;
}

export interface ConversionResult {
  document_id: string;
  conversion_status: string;
  markdown_path: string;
  markdown_preview: string;
  metadata: ConversionMetadata;
  report: ExtractionReport;
}

export interface ChunkManifest {
  document_id: string;
  total_chunks: number;
  total_estimated_tokens: number;
  average_chunk_tokens: number;
  created_at: string;
  chunking_strategy: string;
  source_document_md_sha256: string;
}

export interface ChunkPreview {
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  content_type: string;
  text_preview: string;
  char_count: number;
  estimated_tokens: number;
}

export interface ChunkingResult {
  document_id: string;
  manifest: ChunkManifest;
  chunks_preview: ChunkPreview[];
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: authorizedHeaders(init?.headers) });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    // Support structured error details (dict with message field)
    const detail = err?.detail;
    if (typeof detail === "object" && detail !== null && "message" in detail) {
      throw new Error(detail.message);
    }
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return res.json();
}

export async function uploadFile(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<UploadResult>("/api/files/upload", { method: "POST", body: form });
}

export async function fetchProfile(documentId: string): Promise<DocumentProfile> {
  return apiFetch<DocumentProfile>(`/api/files/${documentId}/profile`);
}

export async function fetchPipeline(documentId: string): Promise<PipelineDecision> {
  return apiFetch<PipelineDecision>(`/api/files/${documentId}/pipeline`);
}

export async function convertDocument(documentId: string): Promise<ConversionResult> {
  return apiFetch<ConversionResult>(`/api/files/${documentId}/convert`, { method: "POST" });
}

export async function getConverted(documentId: string): Promise<ConversionResult> {
  return apiFetch<ConversionResult>(`/api/files/${documentId}/converted`);
}

export async function chunkDocument(documentId: string): Promise<ChunkingResult> {
  return apiFetch<ChunkingResult>(`/api/files/${documentId}/chunk`, { method: "POST" });
}

export async function getChunks(documentId: string): Promise<ChunkingResult> {
  return apiFetch<ChunkingResult>(`/api/files/${documentId}/chunks`);
}

// ── Background Jobs ──────────────────────────────────────────────────────────

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface JobDetail {
  job_id: string;
  document_id: string | null;
  job_type: string;
  status: JobStatus;
  progress_percent: number;
  current_step: string | null;
  message: string | null;
  request: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string | null;
  canceled_at: string | null;
  retry_of_job_id: string | null;
  can_retry: boolean;
  can_cancel: boolean;
}

export interface JobListResponse {
  jobs: JobDetail[];
  total: number;
  limit: number;
  offset: number;
  sort: "newest" | "oldest";
}

export interface JobListFilters {
  documentId?: string;
  status?: JobStatus | "all";
  jobType?: string;
  limit?: number;
  offset?: number;
  sort?: "newest" | "oldest";
}

export interface CleanupJobsRequest {
  older_than_days: number;
  statuses: JobStatus[];
}

export interface CleanupJobsResponse {
  deleted_count: number;
}

export async function fetchJob(jobId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/jobs/${jobId}`);
}

export async function listJobs(filters: JobListFilters = {}): Promise<JobListResponse> {
  const params = new URLSearchParams();
  if (filters.documentId) params.set("document_id", filters.documentId);
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  if (filters.jobType && filters.jobType !== "all") params.set("job_type", filters.jobType);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  if (filters.sort) params.set("sort", filters.sort);
  const query = params.toString();
  return apiFetch<JobListResponse>(`/api/jobs${query ? `?${query}` : ""}`);
}

export async function listDocumentJobs(documentId: string): Promise<JobListResponse> {
  return listJobs({ documentId, limit: 10 });
}

export async function cancelJob(jobId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function retryJob(jobId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/jobs/${jobId}/retry`, { method: "POST" });
}

export async function cleanupJobs(request: CleanupJobsRequest): Promise<CleanupJobsResponse> {
  return apiFetch<CleanupJobsResponse>("/api/jobs/cleanup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function createConvertJob(documentId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/files/${documentId}/convert/job`, { method: "POST" });
}

export async function createChunkJob(documentId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/files/${documentId}/chunk/job`, { method: "POST" });
}

export interface IntegrityCheck {
  name: string;
  status: "pass" | "warn" | "fail" | "skip";
  message: string;
}

export interface IntegrityReport {
  document_id: string;
  status: "pass" | "warn" | "fail";
  checks: IntegrityCheck[];
  warnings: string[];
  errors: string[];
}

export async function fetchIntegrity(documentId: string): Promise<IntegrityReport> {
  return apiFetch<IntegrityReport>(`/api/files/${documentId}/integrity`);
}

export interface OCRStatusResponse {
  document_id: string;
  ocr_enabled: boolean;
  ocr_available: boolean;
  requires_ocr: boolean | null;
  ocr_supported: boolean;
  provider: string;
  language: string;
  warnings: string[];
  error: string | null;
}

export async function fetchOcrStatus(documentId: string): Promise<OCRStatusResponse> {
  return apiFetch<OCRStatusResponse>(`/api/files/${documentId}/ocr-status`);
}

export interface SearchResultItem {
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  content_type: string;
  score: number;
  estimated_tokens: number;
  text_preview: string;
  text: string | null;
}

export interface SearchResponse {
  document_id: string;
  query: string;
  top_k: number;
  total_chunks_searched: number;
  results: SearchResultItem[];
}

export async function searchDocument(
  documentId: string,
  query: string,
  topK: number = 5,
  includeFullText: boolean = false,
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(`/api/files/${documentId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, include_full_text: includeFullText }),
  });
}

export type LLMProvider = "claude" | "openai" | "gemini" | "generic";

export interface PayloadIntegrity {
  all_chunks_verified: boolean;
  verified_count: number;
  failed_chunk_ids: string[];
}

export interface TokenBudgetInfo {
  requested_top_k: number;
  selected_chunk_count: number;
  estimated_context_tokens: number;
  skipped_chunks_due_to_budget: number;
}

export interface LLMPayloadResponse {
  document_id: string;
  provider: string;
  query: string;
  chunks_used: number;
  total_estimated_tokens: number;
  payload_path: string;
  universal_payload: Record<string, unknown>;
  formatted_context: string;
  integrity: PayloadIntegrity;
  token_budget: TokenBudgetInfo;
}

export interface EstimateContextResponse {
  document_id: string;
  provider: string;
  query: string;
  requested_top_k: number;
  selected_chunk_count: number;
  estimated_context_tokens: number;
  skipped_chunks_due_to_budget: number;
  budget_used: number;
}

export async function estimateContext(
  documentId: string,
  query: string,
  budget: number,
  topK: number = 10,
): Promise<EstimateContextResponse> {
  return apiFetch<EstimateContextResponse>(`/api/files/${documentId}/estimate-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, budget }),
  });
}

export async function prepareLlmPayload(
  documentId: string,
  query: string,
  topK: number = 5,
  provider: LLMProvider = "generic",
): Promise<LLMPayloadResponse> {
  return apiFetch<LLMPayloadResponse>(`/api/files/${documentId}/prepare-llm-payload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, provider }),
  });
}

export type GatewayProvider = "mock" | "claude" | "openai" | "gemini";

export interface AskResponse {
  answer: string;
  provider: string;
  chunks_used: number;
  estimated_context_tokens: number;
  payload_id: string;
}

export type EvidenceStrength = "strong" | "moderate" | "weak" | "none";

export interface GroundedCitation {
  citation_id: string;
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  page_number: number | null;
  source_label: string;
  score: number | null;
  text_preview: string;
  estimated_tokens: number;
}

export interface GroundedEvidence {
  evidence_strength: EvidenceStrength;
  retrieved_chunks_count: number;
  citations_count: number;
  total_context_tokens: number;
  top_score: number | null;
  average_score: number | null;
  warnings: string[];
}

export interface GroundedAnswerRequest {
  question: string;
  retrieval_mode: RetrievalMode;
  top_k: number;
  provider: GatewayProvider;
  token_budget?: number | null;
}

export interface GroundedAnswerResponse {
  document_id: string;
  question: string;
  answer: string;
  provider: GatewayProvider;
  retrieval_mode: RetrievalMode;
  citations: GroundedCitation[];
  evidence: GroundedEvidence;
  payload_id: string | null;
  call_id: string | null;
  local_only_mode: boolean;
  warnings: string[];
}

export async function askDocument(
  documentId: string,
  query: string,
  topK: number = 5,
  provider: GatewayProvider = "mock",
  retrievalMode: RetrievalMode = "hybrid",
): Promise<AskResponse> {
  return apiFetch<AskResponse>("/api/llm/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      query,
      top_k: topK,
      provider,
      retrieval_mode: retrievalMode,
    }),
  });
}

export async function askGroundedAnswer(
  documentId: string,
  request: GroundedAnswerRequest,
): Promise<GroundedAnswerResponse> {
  return apiFetch<GroundedAnswerResponse>(`/api/files/${documentId}/grounded-answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function createGroundedAnswerJob(
  documentId: string,
  request: GroundedAnswerRequest,
): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/files/${documentId}/grounded-answer/job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export interface IndexResponse {
  document_id: string;
  qdrant_configured: boolean;
  qdrant_available: boolean;
  collection_name: string;
  indexed_chunks: number;
  collection: string;
  vector_size: number | null;
  embedding_provider: string;
  embedding_model: string;
  status: "indexed";
  qdrant_url_configured: boolean;
  manifest_path: string | null;
}

export interface SemanticSearchResultItem {
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  content_type: string;
  score: number;
  estimated_tokens: number;
  text_preview: string;
  retrieval_mode: "semantic";
}

export interface SemanticSearchResponse {
  document_id: string;
  query: string;
  top_k: number;
  results: SemanticSearchResultItem[];
  search_mode: string;
}

export async function indexDocument(documentId: string): Promise<IndexResponse> {
  return apiFetch<IndexResponse>(`/api/files/${documentId}/index`, { method: "POST" });
}

export async function createIndexJob(documentId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/files/${documentId}/index/job`, { method: "POST" });
}

export async function semanticSearchDocument(
  documentId: string,
  query: string,
  topK: number = 5,
): Promise<SemanticSearchResponse> {
  return apiFetch<SemanticSearchResponse>(`/api/files/${documentId}/semantic-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
}

// ── Vector / Index Status ─────────────────────────────────────────────────────

export interface VectorStatusResponse {
  qdrant_configured: boolean;
  qdrant_available: boolean;
  collection_name: string;
  embedding_provider: string;
  embedding_model: string | null;
  vector_size: number | null;
  lm_studio_base_url: string | null;
  error: string | null;
}

export interface DocumentIndexStatusResponse {
  document_id: string;
  qdrant_configured: boolean;
  qdrant_available: boolean;
  collection_name: string;
  indexed: boolean;
  indexed_chunks: number;
  total_chunks: number | null;
  embedding_provider: string;
  embedding_model: string | null;
  vector_size: number | null;
  indexed_embedding_provider: string | null;
  indexed_embedding_model: string | null;
  indexed_vector_size: number | null;
  error: string | null;
}

export async function fetchVectorStatus(): Promise<VectorStatusResponse> {
  return apiFetch<VectorStatusResponse>("/api/vector/status");
}

export async function fetchDocumentIndexStatus(
  documentId: string,
): Promise<DocumentIndexStatusResponse> {
  return apiFetch<DocumentIndexStatusResponse>(`/api/files/${documentId}/index-status`);
}

export type RetrievalMode = "keyword" | "semantic" | "hybrid";

export interface HybridResultItem {
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  content_type: string;
  combined_score: number;
  keyword_score: number;
  semantic_score: number;
  estimated_tokens: number;
  text_preview: string;
}

export interface HybridSearchResponse {
  document_id: string;
  query: string;
  top_k: number;
  keyword_weight: number;
  semantic_weight: number;
  semantic_available: boolean;
  results: HybridResultItem[];
  search_mode: string;
}

export async function hybridSearchDocument(
  documentId: string,
  query: string,
  topK: number = 8,
  keywordWeight: number = 0.4,
  semanticWeight: number = 0.6,
): Promise<HybridSearchResponse> {
  return apiFetch<HybridSearchResponse>(`/api/files/${documentId}/hybrid-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k: topK,
      keyword_weight: keywordWeight,
      semantic_weight: semanticWeight,
    }),
  });
}

// ── Evaluation API ────────────────────────────────────────────────────────────

export interface TokenEfficiencySummary {
  document_id: string;
  original_estimated_tokens: number | null;
  converted_estimated_tokens: number | null;
  total_chunk_tokens: number | null;
  selected_context_tokens: number | null;
  token_reduction_percent_vs_original: number | null;
  token_reduction_percent_vs_converted: number | null;
  interpretation: string;
  warnings: string[];
}

export interface ChunkQualityReport {
  document_id: string;
  total_chunks: number;
  total_estimated_tokens: number;
  average_chunk_tokens: number;
  min_chunk_tokens: number;
  max_chunk_tokens: number;
  empty_chunks_count: number;
  missing_text_count: number;
  missing_metadata_count: number;
  oversized_chunks_count: number;
  undersized_chunks_count: number;
  duplicate_text_chunks_count: number;
  section_path_coverage_percent: number;
  table_chunks_count: number;
  ocr_chunks_count: number;
  quality_score: number;
  warnings: string[];
  recommendations: string[];
}

export interface RetrievedChunkSummary {
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  content_type: string;
  score: number;
  estimated_tokens: number;
  text_preview: string;
}

export interface RetrievalEvaluationRequest {
  query: string;
  retrieval_mode: RetrievalMode;
  top_k: number;
  expected_terms: string[];
  expected_section?: string | null;
}

export interface RetrievalEvaluationResponse {
  document_id: string;
  query: string;
  retrieval_mode: RetrievalMode;
  top_k: number;
  total_chunks_searched: number;
  returned_chunks_count: number;
  total_context_tokens: number;
  average_result_score: number | null;
  top_score: number | null;
  low_score_results_count: number;
  expected_terms_found: string[];
  expected_terms_missing: string[];
  matched_expected_terms_count: number;
  expected_section: string | null;
  expected_section_hit: boolean | null;
  retrieval_score_estimate: number;
  token_efficiency_estimate: TokenEfficiencySummary;
  selected_results: RetrievedChunkSummary[];
  warnings: string[];
  recommendations: string[];
}

export interface RetrievalEvaluationSetQuery {
  query: string;
  expected_terms: string[];
  expected_section?: string | null;
}

export interface RetrievalEvaluationSetResponse {
  document_id: string;
  retrieval_mode: RetrievalMode;
  top_k: number;
  total_queries: number;
  average_retrieval_score_estimate: number;
  average_context_tokens: number;
  average_token_reduction_percent_vs_converted: number | null;
  queries: RetrievalEvaluationResponse[];
  warnings: string[];
}

export async function fetchChunkQuality(documentId: string): Promise<ChunkQualityReport> {
  return apiFetch<ChunkQualityReport>(`/api/files/${documentId}/chunk-quality`);
}

export async function fetchTokenEfficiency(documentId: string): Promise<TokenEfficiencySummary> {
  return apiFetch<TokenEfficiencySummary>(`/api/files/${documentId}/token-efficiency`);
}

export async function evaluateRetrieval(
  documentId: string,
  request: RetrievalEvaluationRequest,
): Promise<RetrievalEvaluationResponse> {
  return apiFetch<RetrievalEvaluationResponse>(`/api/files/${documentId}/retrieval-evaluation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function createRetrievalEvaluationJob(
  documentId: string,
  request: RetrievalEvaluationRequest,
): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/files/${documentId}/retrieval-evaluation/job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function evaluateRetrievalSet(
  documentId: string,
  retrievalMode: RetrievalMode,
  topK: number,
  queries: RetrievalEvaluationSetQuery[],
): Promise<RetrievalEvaluationSetResponse> {
  return apiFetch<RetrievalEvaluationSetResponse>(`/api/files/${documentId}/retrieval-evaluation-set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ retrieval_mode: retrievalMode, top_k: topK, queries }),
  });
}

// ── Project API ───────────────────────────────────────────────────────────────

export interface Project {
  project_id: string;
  name: string;
  document_ids: string[];
  created_at: string;
}

export interface ProjectSearchResultItem {
  document_id: string;
  source_filename: string;
  chunk_id: string;
  chunk_index: number;
  section_path: string[];
  content_type: string;
  score: number;
  estimated_tokens: number;
  text_preview: string;
  text: string | null;
}

export interface ProjectSearchResponse {
  project_id: string;
  query: string;
  top_k: number;
  documents_searched: number;
  total_chunks_searched: number;
  results: ProjectSearchResultItem[];
}

export type ProjectProvider = "mock" | "claude" | "openai" | "gemini";

export interface ProjectAskResponse {
  answer: string;
  provider: string;
  project_id: string;
  chunks_used: number;
  document_count: number;
  estimated_context_tokens: number;
}

export async function createProject(name: string): Promise<Project> {
  return apiFetch<Project>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/api/projects/${projectId}`);
}

export async function addDocumentToProject(
  projectId: string,
  documentId: string,
): Promise<Project> {
  return apiFetch<Project>(`/api/projects/${projectId}/add-document`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId }),
  });
}

export async function searchProject(
  projectId: string,
  query: string,
  topK: number = 10,
): Promise<ProjectSearchResponse> {
  return apiFetch<ProjectSearchResponse>(`/api/projects/${projectId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export async function askProject(
  projectId: string,
  query: string,
  topK: number = 10,
  provider: ProjectProvider = "mock",
): Promise<ProjectAskResponse> {
  return apiFetch<ProjectAskResponse>(`/api/projects/${projectId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, provider }),
  });
}

// ── Security API ──────────────────────────────────────────────────────────────

export interface UploadSecurityInfo {
  extension: string;
  mime_type: string | null;
  size_bytes: number;
  extension_allowed: boolean;
  size_within_limit: boolean;
  mime_allowed: boolean;
}

export interface InjectionWarning {
  chunk_id: string;
  chunk_index: number;
  matched_pattern: string;
  text_excerpt: string;
}

export interface PayloadSafetyInfo {
  safety_instruction_present: boolean;
  payloads_generated: number;
}

export interface SecurityReport {
  document_id: string;
  generated_at: string;
  local_only_mode: boolean;
  upload: UploadSecurityInfo;
  injection_warnings: InjectionWarning[];
  injection_scan_complete: boolean;
  payload_safety: PayloadSafetyInfo;
  recent_audit_entries: Record<string, unknown>[];
}

export async function fetchSecurityReport(documentId: string): Promise<SecurityReport> {
  return apiFetch<SecurityReport>(`/api/files/${documentId}/security-report`);
}

// ── DB persistence API ────────────────────────────────────────────────────────

export interface DocumentListItem {
  document_id: string;
  original_filename: string;
  mime_type: string | null;
  file_size_bytes: number;
  status: string;
  current_phase: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  total: number;
  documents: DocumentListItem[];
}

export interface ProfileSummary {
  detected_type: string | null;
  mime_type: string | null;
  page_count: number | null;
  requires_ocr: boolean;
  created_at: string;
}

export interface PipelineSummary {
  selected_pipeline: string;
  output_format: string | null;
  created_at: string;
}

export interface ConversionSummary {
  status: string;
  converter_used: string | null;
  estimated_tokens: number | null;
  created_at: string;
}

export interface ChunkSummary {
  total_chunks: number;
  total_estimated_tokens: number | null;
  chunking_strategy: string | null;
  created_at: string;
}

export interface IntegritySummary {
  status: string;
  created_at: string;
}

export interface PayloadSummary {
  payload_id: string;
  provider: string;
  query: string;
  selected_chunk_count: number;
  estimated_context_tokens: number;
  created_at: string;
}

export interface LLMCallSummary {
  call_id: string;
  provider: string;
  query: string;
  status: string;
  created_at: string;
}

export interface DocumentDetail {
  document_id: string;
  original_filename: string;
  mime_type: string | null;
  file_size_bytes: number;
  status: string;
  current_phase: string;
  created_at: string;
  updated_at: string;
  profile: ProfileSummary | null;
  pipeline: PipelineSummary | null;
  conversion: ConversionSummary | null;
  chunks: ChunkSummary | null;
  integrity: IntegritySummary | null;
  recent_payloads: PayloadSummary[];
  recent_llm_calls: LLMCallSummary[];
}

export interface ProjectListItem {
  project_id: string;
  name: string;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  total: number;
  projects: ProjectListItem[];
}

export interface AuditEventItem {
  id: number;
  event_type: string;
  document_id: string | null;
  project_id: string | null;
  payload_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditRecentResponse {
  total: number;
  events: AuditEventItem[];
}

export async function listDocuments(): Promise<DocumentListResponse> {
  return apiFetch<DocumentListResponse>("/api/documents");
}

export async function getDocumentDetail(documentId: string): Promise<DocumentDetail> {
  return apiFetch<DocumentDetail>(`/api/documents/${documentId}`);
}

export async function listProjects(): Promise<ProjectListResponse> {
  return apiFetch<ProjectListResponse>("/api/projects");
}

export async function listRecentAudit(limit: number = 50): Promise<AuditRecentResponse> {
  return apiFetch<AuditRecentResponse>(`/api/audit/recent?limit=${limit}`);
}

export async function getDocumentAudit(
  documentId: string,
  limit: number = 50,
): Promise<AuditRecentResponse> {
  return apiFetch<AuditRecentResponse>(`/api/documents/${documentId}/audit?limit=${limit}`);
}

// ── Document preview ──────────────────────────────────────────────────────────

export interface DocumentPreview {
  document_id: string;
  exists: boolean;
  preview: string;
  char_count: number;
  truncated: boolean;
  source: string;
}

export async function fetchDocumentPreview(
  documentId: string,
  maxChars: number = 12000,
): Promise<DocumentPreview> {
  return apiFetch<DocumentPreview>(`/api/files/${documentId}/preview?max_chars=${maxChars}`);
}

// ── Document initialize ────────────────────────────────────────────────────────

export interface InitializeResult {
  document_id: string;
  profile_created: boolean;
  pipeline_created: boolean;
  current_phase: string;
  warnings: string[];
}

export async function initializeDocument(documentId: string): Promise<InitializeResult> {
  return apiFetch<InitializeResult>(`/api/files/${documentId}/initialize`, { method: "POST" });
}

// ── Paginated documents ────────────────────────────────────────────────────────

export interface DocumentPaginatedResponse {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  documents: DocumentListItem[];
}

export async function listDocumentsPaginated(params: {
  page?: number;
  page_size?: number;
  search?: string;
  phase?: string;
  sort?: "newest" | "oldest";
}): Promise<DocumentPaginatedResponse> {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  if (params.search) q.set("search", params.search);
  if (params.phase) q.set("phase", params.phase);
  if (params.sort) q.set("sort", params.sort);
  const qs = q.toString();
  return apiFetch<DocumentPaginatedResponse>(`/api/documents/paginated${qs ? `?${qs}` : ""}`);
}

// ── Dashboard ──────────────────────────────────────────────────────────────────

export interface DashboardStats {
  total_documents: number;
  total_projects: number;
  completed_documents: number;
  documents_in_progress: number;
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>("/api/dashboard/stats");
}

// ── Export / download ──────────────────────────────────────────────────────────

export type ExportArtifact = "markdown" | "chunks" | "metadata" | "profile" | "pipeline" | "integrity";

async function triggerDownload(url: string, fallbackFilename: string): Promise<void> {
  const res = await fetch(url, { headers: authorizedHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail ?? `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? fallbackFilename;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function exportArtifact(documentId: string, artifact: ExportArtifact): Promise<void> {
  const url = `${API_BASE}/api/files/${documentId}/export?artifact=${artifact}&download=true`;
  await triggerDownload(url, `document_${artifact}`);
}

export async function exportDocumentsCsv(params?: {
  search?: string;
  phase?: string;
  sort?: string;
}): Promise<void> {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.phase) q.set("phase", params.phase);
  if (params?.sort) q.set("sort", params.sort);
  const qs = q.toString();
  const url = `${API_BASE}/api/documents/export.csv${qs ? `?${qs}` : ""}`;
  await triggerDownload(url, "documents_export.csv");
}

// ── Document summary ───────────────────────────────────────────────────────────

export interface DocumentSummary {
  document_id: string;
  original_filename: string;
  mime_type: string | null;
  file_size_bytes: number;
  status: string;
  current_phase: string;
  created_at: string;
  profile: ProfileSummary | null;
  pipeline: PipelineSummary | null;
  conversion: ConversionSummary | null;
  chunks: ChunkSummary | null;
  integrity_status: string | null;
  security_warnings_count: number | null;
  preview_excerpt: string | null;
}

export async function getDocumentSummary(documentId: string): Promise<DocumentSummary> {
  return apiFetch<DocumentSummary>(`/api/documents/${documentId}/summary`);
}
