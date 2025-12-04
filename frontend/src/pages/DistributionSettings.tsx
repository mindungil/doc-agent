import { Link } from 'react-router-dom'
import { useState, useEffect } from 'react'

export default function DistributionSettings() {
  const [scheduledTime, setScheduledTime] = useState('09:00')
  const [isEnabled, setIsEnabled] = useState(false)
  const [saved, setSaved] = useState(false)

  // 로컬스토리지에서 설정 로드
  useEffect(() => {
    const savedTime = localStorage.getItem('distributionTime')
    const savedEnabled = localStorage.getItem('distributionEnabled')

    if (savedTime) setScheduledTime(savedTime)
    if (savedEnabled) setIsEnabled(savedEnabled === 'true')
  }, [])

  const handleSave = () => {
    localStorage.setItem('distributionTime', scheduledTime)
    localStorage.setItem('distributionEnabled', isEnabled.toString())
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

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
              <h1 className="text-3xl font-bold text-gray-900">배부 설정</h1>
              <p className="text-sm text-gray-500 mt-1">자동 배부 시간 및 규칙 설정</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* 저장 성공 메시지 */}
        {saved && (
          <div className="mb-6 bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
            <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-green-800 font-medium">설정이 저장되었습니다.</span>
          </div>
        )}

        {/* 자동 배부 스케줄 설정 */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden mb-6">
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 px-6 py-4 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h2 className="text-xl font-bold text-gray-900">자동 배부 스케줄</h2>
            </div>
          </div>
          <div className="p-6 space-y-6">
            {/* 활성화 토글 */}
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">자동 배부 활성화</h3>
                <p className="text-xs text-gray-600 mt-1">
                  설정된 시간에 자동으로 문서를 배부합니다.
                </p>
              </div>
              <button
                onClick={() => setIsEnabled(!isEnabled)}
                className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                  isEnabled ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`inline-block h-6 w-6 transform rounded-full bg-white transition-transform ${
                    isEnabled ? 'translate-x-7' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* 시간 설정 */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">
                  배부 시간 설정
                </label>
                <div className="flex items-center gap-4">
                  <input
                    type="time"
                    value={scheduledTime}
                    onChange={(e) => setScheduledTime(e.target.value)}
                    disabled={!isEnabled}
                    className="px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-500 text-lg font-mono"
                  />
                  <span className="text-sm text-gray-600">
                    매일 이 시간에 자동 배부가 실행됩니다.
                  </span>
                </div>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex gap-3">
                  <svg className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <div className="text-sm text-blue-900">
                    <p className="font-semibold mb-1">자동 배부 규칙</p>
                    <ul className="list-disc list-inside space-y-1 text-blue-800">
                      <li>유사도 90% 이상인 문서는 과거 담당자에게 자동 배부됩니다.</li>
                      <li>LLM이 담당자를 추천한 경우 해당 담당자에게 배부됩니다.</li>
                      <li>검토가 필요한 문서는 배부되지 않습니다.</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 배부 규칙 설정 (확장 예정) */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden">
          <div className="bg-gradient-to-r from-purple-50 to-pink-50 px-6 py-4 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
              <h2 className="text-xl font-bold text-gray-900">배부 규칙 관리</h2>
            </div>
          </div>
          <div className="p-6">
            <div className="text-center py-8 text-gray-500">
              <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
              <p className="text-sm">추가 배부 규칙 설정 기능이 곧 제공됩니다.</p>
              <p className="text-xs text-gray-400 mt-2">부서별 우선순위, 특정 키워드 규칙 등</p>
            </div>
          </div>
        </div>

        {/* 저장 버튼 */}
        <div className="mt-8 flex justify-end">
          <button
            onClick={handleSave}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:from-blue-700 hover:to-blue-800 font-semibold shadow-lg hover:shadow-xl transition-all duration-200 flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
            </svg>
            설정 저장
          </button>
        </div>
      </main>
    </div>
  )
}
