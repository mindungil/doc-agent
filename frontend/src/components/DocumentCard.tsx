import { useNavigate } from 'react-router-dom'
import type { Document } from '../types'
import { formatToKSTLocale } from '../utils/dateUtils'

interface DocumentCardProps {
  document: Document
}

export default function DocumentCard({ document }: DocumentCardProps) {
  const navigate = useNavigate()

  const getStatusColor = (status: string) => {
    switch (status) {
      case '대기':
        return 'bg-gray-100 text-gray-800'
      case 'RAG 분석 중':
      case 'LLM 분석 중':
        return 'bg-blue-100 text-blue-800'
      case '담당자 추천 완료':
        return 'bg-green-100 text-green-800'
      case '배부 완료':
        return 'bg-purple-100 text-purple-800'
      case '오류':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }


  return (
    <div
      className="bg-white rounded-lg shadow-md p-6 cursor-pointer hover:shadow-lg transition-shadow"
      onClick={() => navigate(`/documents/${document.id}`)}
    >
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-lg font-semibold text-gray-900">{document.title}</h3>
        <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(document.status)}`}>
          {document.status}
        </span>
      </div>
      <div className="text-sm text-gray-600 space-y-1">
        <p>파일명: {document.filename}</p>
        <p>업로드: {formatToKSTLocale(document.uploaded_at)}</p>
        {document.assigned_to && (
          <p className="text-blue-600">담당자: {document.assigned_to}</p>
        )}
      </div>
    </div>
  )
}

