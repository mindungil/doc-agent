import { useQuery } from '@tanstack/react-query'
import { documentApi } from '../api/client'
import { formatToKSTLocale } from '../utils/dateUtils'

export default function AssignmentHistoryTable() {
  const { data: history, isLoading, error } = useQuery({
    queryKey: ['assignment-history'],
    queryFn: () => documentApi.getAssignmentHistory(0, 20),
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">배부 이력</h2>
        <p className="text-red-500 text-center py-8">
          배부 이력을 불러오는 중 오류가 발생했습니다: {error instanceof Error ? error.message : '알 수 없는 오류'}
        </p>
      </div>
    )
  }

  if (!history || history.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">배부 이력</h2>
        <p className="text-gray-500 text-center py-8">배부 완료된 문서가 없습니다.</p>
        <p className="text-gray-400 text-sm text-center mt-2">
          문서를 업로드하고 담당자를 배부하면 여기에 표시됩니다.
        </p>
      </div>
    )
  }


  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">배부 이력</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                문서 제목
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                담당자
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                배부 일시
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                배부 방식
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {history.map((doc) => (
              <tr key={doc.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">{doc.title}</div>
                  <div className="text-sm text-gray-500">{doc.filename}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">{doc.assigned_to || '-'}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatToKSTLocale(doc.assigned_at)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span
                    className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                      doc.is_auto_assigned
                        ? 'bg-green-100 text-green-800'
                        : 'bg-blue-100 text-blue-800'
                    }`}
                  >
                    {doc.is_auto_assigned ? '자동 추천' : '수동 선택'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

