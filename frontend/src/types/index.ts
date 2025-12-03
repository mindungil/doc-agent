export interface Document {
  id: number;
  title: string;
  filename: string;
  status: string;
  uploaded_at: string;
  assigned_to: string | null;
  assigned_at: string | null;
  is_auto_assigned: boolean;
  assigned_dept?: string;  // 배부된 담당자의 부서 정보
}

export interface DocumentDetail extends Document {
  content_preview: string | null;
  recommendation?: AssignmentRecommendation;
}

export interface EmployeeCandidate {
  name: string;
  rank: string;
  dept1: string;
  dept2: string;
  dept3: string;
  tasks: string;
  phone: string | null;
  score?: number;
}

export interface AssignmentRecommendation {
  primary: EmployeeCandidate;
  candidates: EmployeeCandidate[];
  reasoning: string;
}

export interface AssignmentRequest {
  document_id: number;
  employee_name: string;
  employee_dept: string;
  is_auto?: boolean;
}

export interface StatsResponse {
  total_documents_today: number;
  assigned_count: number;
  auto_assigned_count: number;
  manual_assigned_count: number;
}

