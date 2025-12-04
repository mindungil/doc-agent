import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentApi } from '../api/client'
import RecommendationProgress from '../components/RecommendationProgress'
import EmployeeSearch from '../components/EmployeeSearch'
import type { AssignmentRequest, EmployeeCandidate } from '../types'
import { useState } from 'react'
import { formatToKSTLocale } from '../utils/dateUtils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeCandidate | null>(null)

  const documentId = parseInt(id || '0')

  // 처리 중인 상태일 때는 자동으로 폴링
  const { data: document, isLoading } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documentApi.getDocument(documentId),
    enabled: !!documentId,
    refetchInterval: (query) => {
      const data = query.state.data as any
      // 처리 중인 상태면 2초마다 폴링, 완료되면 폴링 중지
      if (data?.status && (
        data.status === '업로드 완료' ||
        data.status === '파싱 중' ||
        data.status === 'OCR 처리 중' ||
        data.status === '텍스트 보정 중' ||
        data.status === 'Pipeline V2 분석 중' ||
        data.status === '담당자 검색 중' ||
        data.status === 'RAG 분석 중' ||
        data.status === 'LLM 분석 중'
      )) {
        return 2000
      }
      return false
    },
  })

  const recommendMutation = useMutation({
    mutationFn: () => documentApi.recommendAssignee(documentId),
    onSuccess: (data) => {
      queryClient.setQueryData(['document', documentId], (old: any) => ({
        ...old,
        recommendation: data,
        status: '담당자 추천 완료',
      }))
    },
  })

  const handleRecommendationComplete = () => {
    queryClient.invalidateQueries({ queryKey: ['document', documentId] })
  }

  const assignMutation = useMutation({
    mutationFn: (request: AssignmentRequest) => documentApi.assignDocument(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      navigate('/documents')
    },
  })

  const handleAssign = () => {
    let employee: EmployeeCandidate

    if (selectedEmployee) {
      employee = selectedEmployee
    } else if (document?.recommendation) {
      employee = document.recommendation.primary
    } else {
      return
    }

    const deptParts = [employee.dept1]
    if (employee.dept2) deptParts.push(employee.dept2)
    if (employee.dept3) deptParts.push(employee.dept3)

    const isFromRecommendation = document?.recommendation && 
      (selectedEmployee?.name === document.recommendation.primary.name ||
       document.recommendation.candidates.some(c => c.name === selectedEmployee?.name))

    assignMutation.mutate({
      document_id: documentId,
      employee_name: employee.name,
      employee_dept: deptParts.join(' '),
      is_auto: isFromRecommendation || false,
    })
  }

  const handleEmployeeSelect = (employee: EmployeeCandidate) => {
    setSelectedEmployee(employee)
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600">로딩 중...</div>
      </div>
    )
  }

  if (!document) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-red-600">문서를 찾을 수 없습니다.</div>
      </div>
    )
  }

  const allCandidates = document.recommendation
    ? [document.recommendation.primary, ...document.recommendation.candidates]
    : []

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <Link to="/documents" className="text-blue-600 hover:text-blue-800 mb-2 inline-block">
            ← 문서 목록으로
          </Link>
          <h1 className="text-3xl font-bold text-gray-900">{document.title}</h1>
          <p className="text-gray-600 mt-1">파일명: {document.filename}</p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">문서 정보</h2>
              <div className="space-y-3 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-gray-600 w-24">상태:</span>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                    document.status === '대기' || document.status === '업로드 완료' ? 'bg-gray-100 text-gray-800' :
                    document.status === '파싱 중' || document.status === 'OCR 처리 중' || document.status === '텍스트 보정 중' ||
                    document.status === 'Pipeline V2 분석 중' || document.status === '담당자 검색 중' ||
                    document.status === 'RAG 분석 중' || document.status === 'LLM 분석 중' ? 'bg-blue-100 text-blue-800' :
                    document.status === '담당자 추천 완료' ? 'bg-green-100 text-green-800' :
                    document.status === '배부 완료' ? 'bg-purple-100 text-purple-800' :
                    document.status.includes('오류') || document.status.includes('실패') ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {document.status}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-600 w-24">업로드 일시:</span>
                  <span className="text-gray-900">{formatToKSTLocale(document.uploaded_at)}</span>
                </div>
                {document.assigned_to && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 w-24">담당자:</span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-blue-600">{document.assigned_to}</span>
                        {document.is_auto_assigned && (
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">자동 배부</span>
                        )}
                      </div>
                      {document.recommendation?.primary && (
                        <div className="text-sm text-gray-600 mt-1 flex items-center gap-2">
                          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                          </svg>
                          <span className="font-medium">
                            {[document.recommendation.primary.dept1, document.recommendation.primary.dept2, document.recommendation.primary.dept3]
                              .filter(Boolean)
                              .join(' ')}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {document.assigned_at && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 w-24">배부 일시:</span>
                    <span className="text-gray-900">{formatToKSTLocale(document.assigned_at)}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">문서 내용 미리보기</h2>
              {document.content_preview ? (
                <div className="bg-gray-50 rounded p-4 max-h-96 overflow-y-auto scrollbar-thin relative scroll-fade-bottom">
                  <pre className="whitespace-pre-wrap text-sm text-gray-700 pb-8">
                    {document.content_preview}
                  </pre>
                  {document.content_preview.length > 500 && (
                    <div className="absolute bottom-2 left-1/2 transform -translate-x-1/2 bg-white px-3 py-1 rounded-full shadow-md text-xs text-gray-500 flex items-center gap-1">
                      <svg className="w-4 h-4 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                      </svg>
                      스크롤하여 더 보기
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-gray-500">내용이 없습니다.</p>
              )}
            </div>

            {!document.recommendation && document.status !== 'RAG 분석 중' && document.status !== 'LLM 분석 중' && (
              <div className="bg-white rounded-lg shadow-md p-6">
                <button
                  onClick={() => recommendMutation.mutate()}
                  disabled={recommendMutation.isPending}
                  className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {recommendMutation.isPending ? '분석 시작 중...' : '담당자 자동 추천'}
                </button>
                {recommendMutation.isError && (
                  <p className="mt-4 text-red-600 text-sm">
                    추천 실패: {recommendMutation.error instanceof Error ? recommendMutation.error.message : '알 수 없는 오류'}
                  </p>
                )}
              </div>
            )}

            {(document.status === '업로드 완료' || document.status === '파싱 중' || document.status === 'OCR 처리 중' ||
              document.status === '텍스트 보정 중' || document.status === 'Pipeline V2 분석 중' || document.status === '담당자 검색 중' ||
              document.status === 'RAG 분석 중' || document.status === 'LLM 분석 중') && (
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">처리 중</h3>
                    <p className="text-sm text-gray-600">{document.status}</p>
                  </div>
                </div>
                <div className="space-y-2 text-sm text-gray-600">
                  <p>• 문서가 처리되고 있습니다. 잠시만 기다려주세요.</p>
                  <p>• 상태는 자동으로 업데이트됩니다.</p>
                </div>
              </div>
            )}
            {(document.status === 'RAG 분석 중' || document.status === 'LLM 분석 중') && document.recommendation && (
              <RecommendationProgress documentId={documentId} onComplete={handleRecommendationComplete} />
            )}
          </div>

          <div className="space-y-6 max-h-[calc(100vh-180px)] overflow-y-auto pr-3 scrollbar-thin relative">
            {/* 스크롤 인디케이터 - 상단 */}
            <div className="sticky top-0 z-10 bg-gradient-to-b from-gray-50 via-gray-50/80 to-transparent pb-3 mb-3 pointer-events-none">
              <div className="flex items-center justify-center gap-2 text-xs text-gray-500">
                <svg className="w-4 h-4 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
                <span className="font-medium">스크롤하여 더 보기</span>
              </div>
            </div>

            {/* LLM 의사결정 과정 표시 - recommendation이 있을 때만 */}
            {document.recommendation?.reasoning && (
              <div className="bg-gradient-to-br from-indigo-50 to-blue-50 rounded-xl shadow-md p-6 border border-indigo-200">
                <div className="flex items-start gap-3">
                  <svg className="w-6 h-6 text-indigo-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                  </svg>
                  <div className="flex-1">
                    <h3 className="text-lg font-bold text-indigo-900 mb-3">🤖 LLM 의사결정 과정</h3>
                    <div className="bg-white rounded-lg p-4 border border-indigo-200 max-h-64 overflow-y-auto scrollbar-thin relative">
                      <div className="text-sm text-gray-800 leading-relaxed pb-2 markdown-content">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({node, ...props}) => <p className="mb-3" {...props} />,
                            strong: ({node, ...props}) => <strong className="font-bold text-gray-900" {...props} />,
                            h1: ({node, ...props}) => <h1 className="text-xl font-bold mb-2 text-gray-900" {...props} />,
                            h2: ({node, ...props}) => <h2 className="text-lg font-bold mb-2 text-gray-900" {...props} />,
                            h3: ({node, ...props}) => <h3 className="text-base font-bold mb-2 text-gray-900" {...props} />,
                            ul: ({node, ...props}) => <ul className="list-disc list-inside mb-3" {...props} />,
                            ol: ({node, ...props}) => <ol className="list-decimal list-inside mb-3" {...props} />,
                            li: ({node, ...props}) => <li className="mb-1" {...props} />,
                            hr: ({node, ...props}) => <hr className="my-4 border-gray-300" {...props} />,
                          }}
                        >
                          {document.recommendation.reasoning}
                        </ReactMarkdown>
                      </div>
                      {document.recommendation.reasoning.length > 200 && (
                        <div className="sticky bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-white via-white to-transparent pointer-events-none flex items-end justify-center pb-1">
                          <svg className="w-4 h-4 text-gray-400 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                          </svg>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {document.recommendation && (
              <>

                {/* 추천 담당자 정보 - 부서 정보 강조 */}
                <div className="bg-white rounded-xl shadow-md p-6 border-2 border-blue-200">
                  <div className="mb-4">
                    <span className="px-3 py-1 bg-blue-600 text-white rounded-full text-sm font-medium">
                      1순위 추천
                    </span>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-2xl font-bold text-gray-900 mb-1">{document.recommendation.primary.name}</h3>
                      <p className="text-gray-600 text-lg">{document.recommendation.primary.rank}</p>
                    </div>
                    <div className="pt-3 border-t border-gray-200">
                      <div className="flex items-start gap-2 mb-2">
                        <svg className="w-5 h-5 text-gray-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <div>
                          <p className="text-xs font-semibold text-gray-500 uppercase mb-1">소속 부서</p>
                          <p className="text-base font-semibold text-gray-900">
                            {[document.recommendation.primary.dept1, document.recommendation.primary.dept2, document.recommendation.primary.dept3]
                              .filter(Boolean)
                              .join(' ')}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3">
                        <p className="text-xs font-semibold text-gray-500 uppercase mb-1">담당 업무</p>
                        <p className="text-sm text-gray-700">{document.recommendation.primary.tasks}</p>
                      </div>
                      {document.recommendation.primary.phone && (
                        <div className="mt-2">
                          <p className="text-xs font-semibold text-gray-500 uppercase mb-1">내선번호</p>
                          <p className="text-sm text-gray-700">{document.recommendation.primary.phone}</p>
                        </div>
                      )}
                      {document.recommendation.primary.score && (
                        <div className="mt-2">
                          <p className="text-xs font-semibold text-gray-500 uppercase mb-1">유사도 점수</p>
                          <p className="text-sm text-gray-700">{document.recommendation.primary.score.toFixed(4)}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {document.recommendation.candidates.length > 0 && (
                  <div className="bg-white rounded-lg shadow-md p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-semibold text-gray-900">다른 후보</h3>
                      {document.recommendation.candidates.length > 2 && (
                        <span className="bg-blue-50 text-blue-600 text-xs px-2 py-1 rounded-full border border-blue-200 font-medium">
                          {document.recommendation.candidates.length}개 후보
                        </span>
                      )}
                    </div>
                    <div className="space-y-4 max-h-96 overflow-y-auto scrollbar-thin pr-2 relative">
                      {/* 스크롤 인디케이터 - 상단 */}
                      {document.recommendation.candidates.length > 2 && (
                        <div className="sticky top-0 z-10 bg-gradient-to-b from-white via-white/90 to-transparent pb-2 mb-2 pointer-events-none">
                          <div className="flex items-center justify-center gap-2 text-xs text-gray-500">
                            <svg className="w-3 h-3 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                            </svg>
                            <span>스크롤하여 더 보기</span>
                          </div>
                        </div>
                      )}
                      {document.recommendation.candidates.map((candidate, idx) => {
                        const deptStr = [candidate.dept1, candidate.dept2, candidate.dept3]
                          .filter(Boolean)
                          .join(' ')
                        return (
                          <div key={idx} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                            <div className="space-y-2">
                              <div>
                                <h4 className="text-lg font-semibold text-gray-900">{candidate.name}</h4>
                                <p className="text-gray-600">{candidate.rank}</p>
                              </div>
                              <div className="flex items-start gap-2">
                                <svg className="w-4 h-4 text-gray-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                <div>
                                  <p className="text-xs font-semibold text-gray-500 uppercase">소속 부서</p>
                                  <p className="text-sm font-medium text-gray-900">{deptStr}</p>
                                </div>
                              </div>
                              <div>
                                <p className="text-xs font-semibold text-gray-500 uppercase">담당 업무</p>
                                <p className="text-sm text-gray-700">{candidate.tasks}</p>
                              </div>
                              {candidate.phone && (
                                <div>
                                  <p className="text-xs font-semibold text-gray-500 uppercase">내선번호</p>
                                  <p className="text-sm text-gray-700">{candidate.phone}</p>
                                </div>
                              )}
                            </div>
                          </div>
                        )
                      })}
                      {/* 스크롤 페이딩 효과 */}
                      {document.recommendation.candidates.length > 2 && (
                        <div className="sticky bottom-0 left-0 right-2 h-12 bg-gradient-to-t from-white via-white to-transparent pointer-events-none flex items-end justify-center pb-2">
                          <svg className="w-4 h-4 text-gray-400 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                          </svg>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div className="bg-white rounded-lg shadow-md p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">담당자 선택</h3>
                  
                  <div className="mb-4">
                    <p className="text-sm text-gray-600 mb-2">추천 후보 중 선택:</p>
                    <select
                      value={selectedEmployee?.name || document.recommendation.primary.name}
                      onChange={(e) => {
                        const emp = allCandidates.find(c => c.name === e.target.value)
                        if (emp) setSelectedEmployee(emp)
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      {allCandidates.map((emp) => (
                        <option key={emp.name} value={emp.name}>
                          {emp.name} ({emp.rank})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="mb-4">
                    <p className="text-sm text-gray-600 mb-2">또는 전체 직원 검색:</p>
                    <EmployeeSearch
                      onSelect={handleEmployeeSelect}
                      excludeNames={allCandidates.map(c => c.name)}
                    />
                  </div>

                  {selectedEmployee && (
                    <div className="mb-4 p-3 bg-blue-50 rounded-lg">
                      <p className="text-sm font-medium text-blue-900">선택된 담당자:</p>
                      <p className="text-sm text-blue-700">
                        {selectedEmployee.name} ({selectedEmployee.rank})
                      </p>
                    </div>
                  )}

                  <button
                    onClick={handleAssign}
                    disabled={assignMutation.isPending}
                    className="w-full px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                  >
                    {assignMutation.isPending ? '처리 중...' : '이 담당자로 확정'}
                  </button>
                  {assignMutation.isError && (
                    <p className="mt-4 text-red-600 text-sm">
                      배부 실패: {assignMutation.error instanceof Error ? assignMutation.error.message : '알 수 없는 오류'}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

