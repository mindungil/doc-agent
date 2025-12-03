import axios from 'axios';
import type { Document, DocumentDetail, AssignmentRecommendation, AssignmentRequest, StatsResponse, EmployeeCandidate } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 요청 인터셉터: 토큰 추가
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터: 401 에러 시 로그인 페이지로 리다이렉트
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const documentApi = {
  uploadDocument: async (file: File): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<Document>('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  getDocuments: async (): Promise<Document[]> => {
    const response = await api.get<Document[]>('/documents/');
    return response.data;
  },

  getDocument: async (id: number): Promise<DocumentDetail> => {
    const response = await api.get<DocumentDetail>(`/documents/${id}`);
    return response.data;
  },

  recommendAssignee: async (id: number): Promise<AssignmentRecommendation> => {
    const response = await api.post<AssignmentRecommendation>(`/documents/${id}/recommend`);
    return response.data;
  },

  assignDocument: async (request: AssignmentRequest): Promise<Document> => {
    const response = await api.post<Document>(`/documents/${request.document_id}/assign`, request);
    return response.data;
  },

  getTodayStats: async (): Promise<StatsResponse> => {
    const response = await api.get<StatsResponse>('/documents/stats/today');
    return response.data;
  },

  getAssignmentHistory: async (skip: number = 0, limit: number = 50): Promise<Document[]> => {
    const response = await api.get<Document[]>('/documents/history', {
      params: { skip, limit },
    });
    return response.data;
  },

  searchEmployees: async (query: string, limit: number = 20): Promise<EmployeeCandidate[]> => {
    const response = await api.get<EmployeeCandidate[]>('/documents/employees/search', {
      params: { query, limit },
    });
    return response.data;
  },
};

export const authApi = {
  login: async (username: string, password: string): Promise<{ success: boolean; token: string; user: string }> => {
    const response = await api.post('/auth/login', { username, password });
    return response.data;
  },

  logout: async (): Promise<void> => {
    await api.post('/auth/logout');
    localStorage.removeItem('auth_token');
  },

  checkStatus: async (): Promise<{ authenticated: boolean; username?: string }> => {
    const response = await api.get('/auth/status');
    return response.data;
  },
};

