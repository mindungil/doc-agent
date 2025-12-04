import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { documentApi } from '../api/client'
import DocumentUpload from '../components/DocumentUpload'
import { formatToKSTShort } from '../utils/dateUtils'

export default function DocumentList() {
  const { data: documents, isLoading, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: documentApi.getDocuments,
  })

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-gray-50">
      <header className="bg-white shadow-lg border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex justify-between items-center">
            <div>
              <Link to="/" className="inline-flex items-center gap-2 text-blue-600 hover:text-blue-800 mb-3 text-sm font-medium hover:gap-3 transition-all">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                대시보드로 돌아가기
              </Link>
              <h1 className="text-3xl font-bold text-gray-900">문서 등록</h1>
            </div>
          </div>
        </div>
      </header>

      <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 max-w-7xl mx-auto">
          <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 px-6 py-4 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <h2 className="text-xl font-bold text-gray-900">문서 업로드</h2>
              </div>
            </div>
            <div className="p-6">
              <DocumentUpload onUploadSuccess={() => refetch()} />
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden max-w-7xl mx-auto">
          <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-blue-50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h2 className="text-lg font-bold text-gray-900">업로드된 문서</h2>
              </div>
              <div className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-semibold">
                총 {documents?.length || 0}개
              </div>
            </div>
          </div>
          {isLoading ? (
            <div className="text-center py-12 text-gray-500">로딩 중...</div>
          ) : !documents || documents.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              업로드된 문서가 없습니다.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full divide-y divide-gray-200 table-fixed">
                <colgroup>
                  <col style={{width: '40%'}} />
                  <col style={{width: '16%'}} />
                  <col style={{width: '13%'}} />
                  <col style={{width: '16%'}} />
                  <col style={{width: '15%'}} />
                </colgroup>
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      문서 정보
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      상태
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      담당자
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      일시
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      작업
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {documents.map((doc) => {
                    const truncateText = (text: string, maxLength: number) => {
                      if (text.length <= maxLength) return text
                      return text.substring(0, maxLength) + '...'
                    }
                    const getStatusDisplay = (status: string) => {
                      // 콜론 앞부분만 추출 (실패 메시지 등에서 상세 내용 제거)
                      const mainStatus = status.split(':')[0].trim()

                      if (mainStatus === 'RAG 분석 중') return 'RAG 분석'
                      if (mainStatus === 'LLM 분석 중') return 'LLM 분석'
                      if (mainStatus === '담당자 추천 완료') return '추천 완료'
                      if (mainStatus === '배부 완료') return '배부 완료'
                      if (mainStatus.includes('파싱 중')) return '파싱 중'
                      if (mainStatus.includes('파싱 실패')) return '파싱 실패'
                      if (mainStatus.includes('자동 선별 실패')) return '선별 실패'
                      if (mainStatus.includes('처리 오류')) return '처리 오류'
                      if (mainStatus.includes('Pipeline V2 실패')) return 'Pipeline 실패'
                      return mainStatus
                    }
                    return (
                      <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-gray-900 truncate" title={doc.title}>
                              {truncateText(doc.title, 50)}
                            </div>
                            <div className="text-xs text-gray-500 mt-1 truncate" title={doc.filename}>
                              {doc.filename}
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2.5 py-1 inline-flex text-xs font-semibold rounded-full whitespace-nowrap ${
                            doc.status === '대기' ? 'bg-gray-100 text-gray-700' :
                            doc.status === 'RAG 분석 중' || doc.status === 'LLM 분석 중' ? 'bg-blue-100 text-blue-700' :
                            doc.status === '담당자 추천 완료' ? 'bg-green-100 text-green-700' :
                            doc.status === '배부 완료' ? 'bg-purple-100 text-purple-700' :
                            doc.status.includes('오류') || doc.status.includes('실패') ? 'bg-red-100 text-red-700' :
                            'bg-gray-100 text-gray-700'
                          }`} title={doc.status}>
                            {getStatusDisplay(doc.status)}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          {doc.assigned_to ? (
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-blue-600 truncate">{doc.assigned_to}</div>
                              {doc.assigned_dept && (
                                <div className="text-xs text-gray-500 mt-0.5 truncate" title={doc.assigned_dept}>
                                  {truncateText(doc.assigned_dept, 20)}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-sm text-gray-400">-</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm text-gray-600 space-y-0.5">
                            <div className="text-xs text-gray-500">업로드: {formatToKSTShort(doc.uploaded_at)}</div>
                            {doc.assigned_at && (
                              <div className="text-xs text-gray-500">배부: {formatToKSTShort(doc.assigned_at)}</div>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <Link
                            to={`/documents/${doc.id}`}
                            className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-md transition-colors"
                          >
                            상세보기
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

