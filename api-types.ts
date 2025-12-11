/**
 * TypeScript Type Definitions for Document Intelligence API v1.0
 * Generated on: 2025-08-23 10:35:26
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

// ==================== DOCUMENT TYPES ====================

export interface DocumentResponse {
  id: string;
  org_id: string;
  filename: string;
  original_filename: string;
  file_type: FileType;
  file_size: number;
  storage_path: string;
  status: DocumentStatus;
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
  }
} as const;

// ==================== REACT QUERY KEYS ====================

/**
 * React Query keys for consistent cache management
 */
export const QUERY_KEYS = {
  DOCUMENTS: ['documents'],
  DOCUMENT: (id: string) => ['documents', id],
  DOCUMENTS_LIST: (filters?: DocumentFilters, pagination?: PaginationParams) =>
    ['documents', 'list', filters, pagination],
} as const;

// ==================== CONSTANTS ====================

export const FILE_SIZE_LIMITS = {
  MAX_FILE_SIZE: 50 * 1024 * 1024, // 50MB
} as const;

export const SUPPORTED_FILE_TYPES = {
  PDF: 'application/pdf',
  XLSX: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
} as const;
