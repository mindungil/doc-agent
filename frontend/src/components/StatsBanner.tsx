import { useQuery } from '@tanstack/react-query'
import { documentApi } from '../api/client'

export default function StatsBanner() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats', 'today'],
    queryFn: documentApi.getTodayStats,
    refetchInterval: 30000, // 30초마다 갱신
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow border border-gray-200 mb-6">
        <div className="animate-pulse">
          <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
            <div className="h-5 bg-gray-200 rounded w-1/4"></div>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="border border-gray-200 rounded-lg p-5">
                  <div className="h-20 bg-gray-200 rounded"></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!stats) return null

  const assignedRate = stats.total_documents_today > 0
    ? ((stats.assigned_count / stats.total_documents_today) * 100).toFixed(0)
    : 0

  const autoRate = stats.assigned_count > 0
    ? ((stats.auto_assigned_count / stats.assigned_count) * 100).toFixed(0)
    : 0

  const pendingCount = stats.total_documents_today - stats.assigned_count

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 mb-6">
      <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <h2 className="text-lg font-semibold text-gray-900">오늘 처리 현황</h2>
          </div>
          <div className="text-sm text-gray-500">
            처리율: <span className="font-semibold text-gray-700">{assignedRate}%</span>
          </div>
        </div>
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* 전체 문서 */}
          <div className="border border-gray-200 rounded-lg p-5 bg-white hover:bg-gray-50 transition-colors">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 bg-blue-100 rounded">
                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <p className="text-sm text-gray-600">전체 문서</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_documents_today}</p>
              </div>
            </div>
            <p className="text-xs text-gray-500">오늘 업로드</p>
          </div>

          {/* 배부 완료 */}
          <div className="border border-gray-200 rounded-lg p-5 bg-white hover:bg-gray-50 transition-colors">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 bg-green-100 rounded">
                <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <p className="text-sm text-gray-600">배부 완료</p>
                <p className="text-2xl font-bold text-gray-900">{stats.assigned_count}</p>
              </div>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-green-600 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${assignedRate}%` }}
              ></div>
            </div>
          </div>

          {/* 자동 배부 */}
          <div className="border border-gray-200 rounded-lg p-5 bg-white hover:bg-gray-50 transition-colors">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 bg-purple-100 rounded">
                <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div>
                <p className="text-sm text-gray-600">자동 배부</p>
                <p className="text-2xl font-bold text-gray-900">{stats.auto_assigned_count}</p>
              </div>
            </div>
            <p className="text-xs text-gray-500">자동화율 {autoRate}%</p>
          </div>

          {/* 대기 중 */}
          <div className="border border-gray-200 rounded-lg p-5 bg-white hover:bg-gray-50 transition-colors">
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 bg-orange-100 rounded">
                <svg className="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <p className="text-sm text-gray-600">처리 대기</p>
                <p className="text-2xl font-bold text-gray-900">{pendingCount}</p>
              </div>
            </div>
            <p className="text-xs text-gray-500">배부 대기 중</p>
          </div>
        </div>
      </div>
    </div>
  )
}

