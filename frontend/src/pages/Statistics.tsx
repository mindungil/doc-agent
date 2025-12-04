import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { documentApi } from '../api/client'

interface DailyStats {
  date: string
  total: number
  auto_assigned: number
  manual_assigned: number
}

export default function Statistics() {
  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: documentApi.getDocuments,
  })

  // 일별 통계 계산
  const calculateDailyStats = (): DailyStats[] => {
    if (!documents) return []

    const statsMap = new Map<string, DailyStats>()

    documents.forEach((doc) => {
      const date = new Date(doc.uploaded_at).toISOString().split('T')[0]

      if (!statsMap.has(date)) {
        statsMap.set(date, {
          date,
          total: 0,
          auto_assigned: 0,
          manual_assigned: 0,
        })
      }

      const stats = statsMap.get(date)!
      stats.total++

      if (doc.assigned_to) {
        if (doc.is_auto_assigned) {
          stats.auto_assigned++
        } else {
          stats.manual_assigned++
        }
      }
    })

    return Array.from(statsMap.values())
      .sort((a, b) => b.date.localeCompare(a.date))
  }

  const dailyStats = calculateDailyStats()

  // 전체 통계
  const totalDocs = documents?.length || 0
  const assignedDocs = documents?.filter(d => d.assigned_to).length || 0
  const autoAssignedDocs = documents?.filter(d => d.is_auto_assigned).length || 0

  // 자동 배정률
  const autoAssignmentRate = assignedDocs > 0
    ? ((autoAssignedDocs / assignedDocs) * 100).toFixed(1)
    : '0.0'

  // 부서별 통계
  const deptStats = documents?.reduce((acc, doc) => {
    if (doc.assigned_to) {
      // filtered_departments에서 부서 정보 추출 시도
      const dept = doc.assigned_dept || '미분류'
      acc[dept] = (acc[dept] || 0) + 1
    }
    return acc
  }, {} as Record<string, number>) || {}

  const topDepts = Object.entries(deptStats)
    .sort(([,a], [,b]) => b - a)
    .slice(0, 10)

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
              <h1 className="text-3xl font-bold text-gray-900">처리 현황 통계</h1>
              <p className="text-sm text-gray-500 mt-1">전체 문서 배부 이력 및 통계</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* 전체 요약 통계 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">전체 문서</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">{totalDocs}</p>
              </div>
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">배부 완료</p>
                <p className="text-3xl font-bold text-green-600 mt-2">{assignedDocs}</p>
              </div>
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">자동 배정</p>
                <p className="text-3xl font-bold text-purple-600 mt-2">{autoAssignedDocs}</p>
              </div>
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">자동 배정률</p>
                <p className="text-3xl font-bold text-indigo-600 mt-2">{autoAssignmentRate}%</p>
              </div>
              <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* 일별 통계 */}
          <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-bold text-gray-900">일별 처리 현황</h2>
            </div>
            <div className="p-6 max-h-[600px] overflow-y-auto">
              {isLoading ? (
                <div className="text-center py-12 text-gray-500">로딩 중...</div>
              ) : dailyStats.length === 0 ? (
                <div className="text-center py-12 text-gray-500">데이터가 없습니다.</div>
              ) : (
                <div className="space-y-4">
                  {dailyStats.map((stat) => (
                    <div key={stat.date} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-sm font-semibold text-gray-900">{stat.date}</span>
                        <span className="text-sm text-gray-600">총 {stat.total}건</span>
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">자동 배정</span>
                          <span className="font-medium text-purple-600">{stat.auto_assigned}건</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">수동 배정</span>
                          <span className="font-medium text-blue-600">{stat.manual_assigned}건</span>
                        </div>
                      </div>
                      <div className="mt-3">
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-gradient-to-r from-purple-500 to-blue-500 h-2 rounded-full transition-all"
                            style={{ width: `${(stat.auto_assigned + stat.manual_assigned) / stat.total * 100}%` }}
                          ></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 부서별 통계 */}
          <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden">
            <div className="bg-gradient-to-r from-green-50 to-emerald-50 px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-bold text-gray-900">부서별 배부 현황</h2>
              <p className="text-sm text-gray-600 mt-1">상위 10개 부서</p>
            </div>
            <div className="p-6 max-h-[600px] overflow-y-auto">
              {isLoading ? (
                <div className="text-center py-12 text-gray-500">로딩 중...</div>
              ) : topDepts.length === 0 ? (
                <div className="text-center py-12 text-gray-500">데이터가 없습니다.</div>
              ) : (
                <div className="space-y-4">
                  {topDepts.map(([dept, count], index) => (
                    <div key={dept} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                      <div className="flex items-center gap-4">
                        <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg flex items-center justify-center text-white font-bold text-lg">
                          {index + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold text-gray-900 truncate" title={dept}>
                            {dept}
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            {count}건 배부
                          </div>
                        </div>
                        <div className="flex-shrink-0">
                          <span className="text-2xl font-bold text-green-600">{count}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
