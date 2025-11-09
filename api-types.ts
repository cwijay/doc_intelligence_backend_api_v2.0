/**
 * TypeScript Type Definitions for Document Intelligence API v1.0
 * Generated on: 2025-08-23 10:35:26
 * 
 * 🚀 Updated with AI Content Support
 * - DocumentResponse now includes AI fields (summary, faq, questions)
 * - DocumentSummarizeResponse uses saved_to_firestore instead of GCS
 * - New DocumentAIContent types for dedicated AI content management
 */

// ==================== ENUMS ====================

export enum DocumentStatus {
  UPLOADING = "uploading",
  UPLOADED = "uploaded", 
  PARSING = "parsing",
  PARSED = "parsed",
  FAILED = "failed"
}

export enum FileType {
  PDF = "pdf",
  XLSX = "xlsx"
}

// ==================== BASE TYPES ====================

export interface PaginationParams {
  page?: number;
  per_page?: number;
}

export interface DocumentFilters {
  filename?: string;
  file_type?: FileType;
  status?: DocumentStatus;
  folder_id?: string;
  uploaded_by?: string;
  is_active?: boolean;
  created_after?: string;
  created_before?: string;
}

// ==================== AI CONTENT TYPES ====================

export interface FAQItem {
  question: string;
  answer: string;
}

export interface DocumentAIContentRequest {
  summary?: string;
  faq?: FAQItem[];
  questions?: string[];
}

export interface DocumentAIContentResponse {
  document_id: string;
  filename: string;
  summary?: string;
  faq: FAQItem[];
  questions: string[];
  has_ai_content: boolean;
  ai_content_size: number;
  updated_at: string;
}

// ==================== DOCUMENT TYPES ====================

/**
 * 🔥 UPDATED: DocumentResponse now includes AI content fields
 */
export interface DocumentResponse {
  id: string;
  org_id: string;
  filename: string;
  original_filename: string;
  file_type: FileType;
  file_size: number;
  storage_path: string;
  status: DocumentStatus;
  parsed_storage_path?: string;
  parsing_metadata?: Record<string, any>;
  file_content?: string;
  
  // 🤖 NEW: AI-generated content fields
  summary?: string;
  faq: FAQItem[];
  questions: string[];
  
  folder_id?: string;
  metadata: Record<string, any>;
  uploaded_by: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentList {
  documents: DocumentResponse[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface DocumentUploadResponse {
  success: boolean;
  message: string;
  document: DocumentResponse;
  upload_time_ms?: number;
}

export interface DocumentDeleteResponse {
  success: boolean;
  message: string;
}

export interface DocumentStatusUpdate {
  status: DocumentStatus;
  metadata?: Record<string, any>;
}

// ==================== DOCUMENT PROCESSING TYPES ====================

export interface DocumentParseRequest {
  filename: string;
  force_reparse?: boolean;
  parse_options?: Record<string, any>;
}

export interface DocumentParseResponse {
  success: boolean;
  document_id: string;
  filename: string;
  parsed_content: string;
  parsing_metadata: Record<string, any>;
  storage_path: string;
  timestamp: string;
}

// ==================== SUMMARIZATION TYPES ====================

export interface DocumentSummaryMetadata {
  created_at: string;
  model: string;
  content_length: number;
  summary_length: number;
  original_filename?: string;
  original_storage_path?: string;
  processing_time_ms?: number;
}

export interface DocumentSummarizeRequest {
  filename: string;
  include_metadata?: boolean;
  summary_type?: "brief" | "comprehensive" | "executive";
}

/**
 * 🔥 UPDATED: DocumentSummarizeResponse now saves to Firestore
 * ❌ Removed: summary_storage_path, gcs_url
 * ✅ Added: saved_to_firestore
 */
export interface DocumentSummarizeResponse {
  success: boolean;
  document_id: string;
  filename: string;
  original_storage_path: string;
  summary_content: string;
  summary_metadata: DocumentSummaryMetadata;
  saved_to_firestore: boolean;  // 🔥 NEW: Replaces GCS fields
  timestamp: string;
  document_metadata?: Record<string, any>;
}

// ==================== API CLIENT TYPES ====================

export interface APIResponse<T = any> {
  data?: T;
  error?: string;
  status: number;
}

export interface AuthHeaders {
  Authorization: `Bearer ${string}`;
}

// ==================== UTILITY TYPES ====================

/**
 * Helper type for documents with AI content
 */
export type DocumentWithAI = DocumentResponse & {
  summary: string;
  faq: FAQItem[];
  questions: string[];
};

/**
 * Helper type to check if document has AI content
 */
export const hasAIContent = (doc: DocumentResponse): doc is DocumentWithAI => {
  return !!(doc.summary || doc.faq.length > 0 || doc.questions.length > 0);
};

/**
 * Helper type for partial document updates
 */
export type DocumentUpdate = Partial<Pick<DocumentResponse, 'metadata' | 'folder_id'>>;

// ==================== API ENDPOINTS ====================

/**
 * API endpoint paths for type-safe route construction
 */
export const API_ROUTES = {
  DOCUMENTS: {
    LIST: '/api/v1/documents',
    GET: (id: string) => `/api/v1/documents/${id}`,
    UPLOAD: '/api/v1/documents/upload',
    DELETE: (id: string) => `/api/v1/documents/${id}`,
    DOWNLOAD: (id: string) => `/api/v1/documents/${id}/download`,
    UPDATE_STATUS: (id: string) => `/api/v1/documents/${id}/status`,
    PARSE: (filename: string) => `/api/v1/documents/parse/${filename}`,
    SUMMARIZE: (filename: string) => `/api/v1/documents/summarize/${filename}`,
    AI_CONTENT: {
      GET: (id: string) => `/api/v1/documents/${id}/ai-content`,
      UPDATE: (id: string) => `/api/v1/documents/${id}/ai-content`,
    }
  }
} as const;

// ==================== REACT QUERY KEYS ====================

/**
 * React Query keys for consistent cache management
 */
export const QUERY_KEYS = {
  DOCUMENTS: ['documents'],
  DOCUMENT: (id: string) => ['documents', id],
  DOCUMENT_AI_CONTENT: (id: string) => ['documents', id, 'ai-content'],
  DOCUMENTS_LIST: (filters?: DocumentFilters, pagination?: PaginationParams) => 
    ['documents', 'list', filters, pagination],
} as const;

// ==================== CONSTANTS ====================

export const FILE_SIZE_LIMITS = {
  MAX_FILE_SIZE: 50 * 1024 * 1024, // 50MB
  MAX_SUMMARY_SIZE: 10 * 1024,     // 10KB
  MAX_FAQ_SIZE: 5 * 1024,          // 5KB  
  MAX_QUESTIONS_SIZE: 3 * 1024,    // 3KB
} as const;

export const SUPPORTED_FILE_TYPES = {
  PDF: 'application/pdf',
  XLSX: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
} as const;

/**
 * 🔄 MIGRATION GUIDE for existing Next.js code:
 * 
 * 1. DocumentResponse now includes AI fields:
 *    - summary?: string
 *    - faq: FAQItem[]  
 *    - questions: string[]
 * 
 * 2. DocumentSummarizeResponse changes:
 *    - ❌ Removed: summary_storage_path, gcs_url
 *    - ✅ Added: saved_to_firestore: boolean
 * 
 * 3. New endpoints available:
 *    - GET /documents/{id}/ai-content
 *    - PATCH /documents/{id}/ai-content
 * 
 * 4. All AI fields are optional - existing code continues to work
 * 
 * 5. Use hasAIContent() helper to check for AI content availability
 */
